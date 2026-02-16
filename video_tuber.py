import os
import time
import random
import queue
import socket
import threading

import numpy as np
import cv2
import sounddevice as sd

# ---------------- CONFIG ----------------
WINDOW_NAME = "Camera :3"
SCREEN_WIDTH = 350
SCREEN_HEIGHT = 350

MIC_DEVICE_INDEX = 1
AUDIO_THRESHOLD_NOISE = 0.2
NOISE_DURATION = 0.0
AUDIO_THRESHOLD_SILENCE = 0.2
SILENCE_DURATION = 1.0

HOST = '0.0.0.0'
PORT = 5000

VIDEO_END_CUTOFF = 20

TRANSITION_FILTER_FRAMES = 5
GLITCH_ENABLE = True
GLITCH_SHIFT = 25
GLITCH_BAR_MIN = 5
GLITCH_BAR_MAX = 10
BLUE_BOOST = 80

ENABLE_VHS = True
VHS_AMPLITUDE = 2
VHS_FREQ = 10.0
SCANLINE_ENABLE = True
SCANLINE_OPACITY = 160
SCANLINE_SPACING = 4
ENABLE_CA = True
CA_SHIFT = 4

# ---------------- GLOBAL VARIABLES ----------------
FRAME_ENDED = False
video_requests = queue.Queue()
sm_video_request = queue.Queue()
audio_queue = queue.Queue()
midi_queue = queue.Queue()
log_queue = queue.Queue()

# ---------------- SAFE PRINT ----------------
def safe_print(*args, **kwargs):
    log_queue.put((args, kwargs))

def process_logs():
    while not log_queue.empty():
        args, kwargs = log_queue.get()
        print(*args, **kwargs)

# ---------------- STATE STRUCTURE ----------------
class StateStruct:
    def __init__(self, name, video_random, videos=None, transitions=None):
        self.name = name
        self.videos = videos if videos else []
        self.video_random = video_random
        self.transitions = transitions if transitions else []

    def __repr__(self):
        return f"StateStruct({self.name!r}, videos={self.videos!r}, video_random={self.video_random!r}, transitions={self.transitions!r})"

# ---------------- DEFINE STATES ----------------
STATES = {
    "Idle": StateStruct(
        name="Idle",
        video_random=True,
        transitions=[("Talking", "MIC", (AUDIO_THRESHOLD_NOISE, NOISE_DURATION, "POSITIVE")),
                     ("Emotes", "MIDI", (None))]
    ),
    "Talking": StateStruct(
        name="Talking",
        video_random=True,
        transitions=[("Idle", "MIC", (AUDIO_THRESHOLD_SILENCE, SILENCE_DURATION, "NEGATIVE")),
                     ("Emotes", "MIDI", (None))]
    ),
    "Emotes": StateStruct(
        name="Emotes",
        video_random=False,
        transitions=[("Idle", "Inactivity", (None))]
    ),
}

# ---------------- AUTO-LOAD VIDEOS ----------------
def auto_load_videos_into_states(state_map):
    video_ext = (".mp4", ".mov", ".avi", ".mkv")
    for state_name, state_struct in state_map.items():
        folder_path = os.path.join(os.getcwd(), state_name)
        matched_files = []
        if os.path.isdir(folder_path):
            for file in os.listdir(folder_path):
                if file.lower().endswith(video_ext):
                    matched_files.append(os.path.join(folder_path, file))
        else:
            safe_print(f"Warning: folder '{folder_path}' does not exist.")
        state_struct.videos = matched_files

# ---------------- Filters ---------------------
class Filters:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.transition_filter_active = False
        self.transition_filter_frames_remaining = 0
        self.TRANSITION_FILTER_TOTAL_FRAMES = TRANSITION_FILTER_FRAMES
        self.LAST_CLEAN_FRAME = np.zeros((screen_height, screen_width, 3), dtype=np.uint8)

    def generate_glitch_frame(self, base_frame):
        base = base_frame.copy()
        self.LAST_CLEAN_FRAME = base_frame.copy()
        num_bars = random.randint(GLITCH_BAR_MIN, GLITCH_BAR_MAX)
        for _ in range(num_bars):
            y = random.randint(0, self.screen_height - 2)
            h = random.randint(1, min(10, self.screen_height - y))
            shift = random.randint(-GLITCH_SHIFT, GLITCH_SHIFT)
            x_r = max(0, shift)
            base[y:y+h, x_r:self.screen_width, 0] = 255
            x_g = max(0, -shift)
            base[y:y+h, x_g:self.screen_width, 1] = 255
            blue = base[y:y+h, :, 2].astype(np.int16) + BLUE_BOOST
            base[y:y+h, :, 2] = np.clip(blue, 0, 255).astype(np.uint8)
        return base

    def apply_scanlines(self, frame):
        if not SCANLINE_ENABLE:
            return frame
        out = frame.copy()
        for y in range(0, out.shape[0], SCANLINE_SPACING):
            darkened = out[y:y+1].astype(np.int16) - SCANLINE_OPACITY
            out[y:y+1] = np.clip(darkened, 0, 255).astype(np.uint8)
        return out

    def apply_chromatic_aberration(self, frame):
        if not ENABLE_CA:
            return frame
        b, g, r = cv2.split(frame)
        r_shift = np.roll(r, CA_SHIFT, axis=1)
        g_shift = np.roll(g, -CA_SHIFT, axis=0)
        return cv2.merge([b, g_shift, r_shift])

    def apply_vhs_wobble(self, frame):
        if not ENABLE_VHS:
            return frame
        h = frame.shape[0]
        t = time.time()
        out = np.empty_like(frame)
        rows = np.arange(h)
        shifts = (VHS_AMPLITUDE * np.sin(rows / VHS_FREQ + t * 8.0)).astype(np.int32)
        for i, s in enumerate(shifts):
            out[i] = np.roll(frame[i], s, axis=0) if s != 0 else frame[i]
        return out

    def apply_filters(self, frame):
        if GLITCH_ENABLE and self.transition_filter_active:
            frame = self.generate_glitch_frame(frame)
            self.transition_filter_frames_remaining -= 1
            if self.transition_filter_frames_remaining <= 0:
                self.transition_filter_active = False
        frame = self.apply_vhs_wobble(frame)
        frame = self.apply_chromatic_aberration(frame)
        frame = self.apply_scanlines(frame)
        return frame

    def start_transition_filter(self):
        self.transition_filter_active = True
        self.transition_filter_frames_remaining = self.TRANSITION_FILTER_TOTAL_FRAMES

# ---------------- VIDEO PLAYER ----------------
class VideoPlayer:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.current_video = None
        self.cap = None
        self.current_state = None

    def select_random_video(self, video_list):
        if video_list:
            self.current_video = random.choice(video_list)
            if self.cap:
                self.cap.release()
            self.cap = cv2.VideoCapture(self.current_video)
            safe_print(f"Selected video: {self.current_video}")
        else:
            self.current_video = None
            self.cap = None
            safe_print("No videos available to play.")

    def select_new_video(self):
        while not sm_video_request.empty():
            requested_name = sm_video_request.get()
        matched = None
        for v in self.current_state.videos:
            if (requested_name.lower()+".mp4") == os.path.basename(v).lower():
                matched = v
                break
        if matched:
            if self.cap:
                self.cap.release()
            self.current_video = matched
            self.cap = cv2.VideoCapture(matched)
            safe_print(f"Loaded video: {matched}")
        else:
            safe_print(f"No video found matching {requested_name}")

    def get_frame(self):
        global FRAME_ENDED
        if not self.cap:
            return None
        frame_idx = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        near_end = total_frames > 0 and frame_idx >= total_frames - VIDEO_END_CUTOFF
        ret, frame = self.cap.read()
        if not ret or (near_end and self.current_state.video_random):
            self.start_transition_filter()
            self.select_random_video(self.current_state.videos)
            ret, frame = self.cap.read()
            FRAME_ENDED = False
        if near_end:
            FRAME_ENDED = True
        if frame is not None:
            frame = cv2.resize(frame, (self.screen_width, self.screen_height))
        return frame

    def release(self):
        if self.cap:
            self.cap.release()

# ---------------- STATE MACHINE ----------------
class StateMachine(VideoPlayer, Filters):
    def __init__(self, states, initial_state="Idle"):
        VideoPlayer.__init__(self, SCREEN_WIDTH, SCREEN_HEIGHT)
        Filters.__init__(self, SCREEN_WIDTH, SCREEN_HEIGHT)
        self.states = states
        self.current_state = states[initial_state]
        self.select_random_video(self.current_state.videos)

    def update(self):
        for next_state_name, rule_name, config in self.current_state.transitions:
            for r_name, init_fn, callback_fn in RULES:
                if r_name == rule_name:
                    if config is None:
                        result = callback_fn()
                    else:
                        result = callback_fn(*config)
                    if result:
                        self.start_transition_filter()
                        self.switch_state(next_state_name)

    def switch_state(self, new_state_name):
        global FRAME_ENDED
        if new_state_name in self.states:
            self.current_state = self.states[new_state_name]
            safe_print(f"Switched to state: {new_state_name}")
            if self.current_state.video_random:
                self.select_random_video(self.current_state.videos)
            else:
                self.select_new_video()
        else:
            safe_print(f"State {new_state_name} not found, switching to Idle")
            self.current_state = self.states["Idle"]
            self.select_random_video(self.current_state.videos)
        FRAME_ENDED = False

# ---------------- RULES ----------------
# MIC
VOLUME = 0.0
SOUND_DETECTED = False
LAST_NOISE_TIME = 0.0

def audio_callback(indata, frames, time_info, status):
    volume = np.linalg.norm(indata)
    audio_queue.put(volume)

def mic_init():
    stream = sd.InputStream(device=MIC_DEVICE_INDEX, channels=1, callback=audio_callback)
    stream.start()
    return stream

def mic_callback(threshold, duration, threshold_type):
    global SOUND_DETECTED, LAST_NOISE_TIME
    result = False
    try:
        while True:
            vol = audio_queue.get_nowait()
            if threshold_type=="POSITIVE":
                passed = vol >= threshold
            else:
                passed = vol <= threshold
            now = time.time()
            if passed:
                if not SOUND_DETECTED:
                    SOUND_DETECTED = True
                    LAST_NOISE_TIME = now
                elif now - LAST_NOISE_TIME > duration:
                    result = True
                    SOUND_DETECTED = False
            else:
                SOUND_DETECTED = False
    except queue.Empty:
        pass
    return result

# Inactivity
def inactivity_init():
    pass
def inactivity_callback():
    return FRAME_ENDED

# MIDI
def handle_client(client_socket, address, stop_event):
    client_socket.settimeout(1.0)
    with client_socket:
        while not stop_event.is_set():
            try:
                print("waiting for data")
                data = client_socket.recv(1024)
                print("data")
                if not data:
                    break
                print("decode")
                msg = data.decode('utf-8').strip()
                print("decode after")
                print(f"[{address}] Received raw: {msg}")
                first_param = msg.split(",",1)[0].strip()
                video_requests.put(first_param)
            except socket.timeout:
                continue
            except:
                break

def midi_server_thread(server, stop_event):
    server.settimeout(1.0)
    while not stop_event.is_set():
        try:
            print("Waiting...")
            client_socket, address = server.accept()
            print(f"Client connected {address}")
            thread = threading.Thread(target=handle_client, args=(client_socket, address, stop_event))
            thread.start()
        except socket.timeout:
            continue

def midi_init(stop_event):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print("Listening for connections")
    thread = threading.Thread(target=midi_server_thread, args=(server, stop_event))
    thread.start()
    return server, thread

def midi_callback():
    result = False
    try:
        while True:
            v = video_requests.get_nowait()
            sm_video_request.put(v)
            result = True
    except queue.Empty:
        pass
    return result

RULES = [
    ("MIC", mic_init, mic_callback),
    ("Inactivity", inactivity_init, inactivity_callback),
    ("MIDI", midi_init, midi_callback),
]

# ---------------- MAIN ----------------
if __name__ == "__main__":
    auto_load_videos_into_states(STATES)
    stop_event = threading.Event()
    sm = StateMachine(STATES)

    # Initialize rules
    streams = []
    for name, init_fn, cb_fn in RULES:
        if name == "MIC":
            streams.append(init_fn())
        elif name == "MIDI":
            server, server_thread = init_fn(stop_event)
        else:
            init_fn()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, SCREEN_WIDTH, SCREEN_HEIGHT)

    try:
        while True:
            process_logs()
            sm.update()
            frame = sm.get_frame()
            if frame is not None:
                frame = sm.apply_filters(frame)
                cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(30) & 0xFF == 27:
                break
    finally:
        stop_event.set()
        server.close()
        for s in streams:
            s.stop()
        cv2.destroyAllWindows()
        safe_print("Application exited cleanly.")
        process_logs()
