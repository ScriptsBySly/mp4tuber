import os
import mido
import time
import threading

from midi_config import MidiConfigManager

# ---------------- CONFIG ----------------
MIDI_CONFIG_FOLDER = "midi_configs"


class MidiLedController:
    def resolve_output_name(self, device_names):
        outputs = mido.get_output_names()
        for name in device_names:
            if name in outputs:
                return name
        for name in device_names:
            if not name:
                continue
            prefix = name.rsplit(" ", 1)[0]
            for out in outputs:
                if out.startswith(prefix):
                    return out
        if len(outputs) == 1:
            return outputs[0]
        return None

    def set_led(self, device_name, note, velocity):
        out_name = self.resolve_output_name([device_name])
        if not out_name:
            return False
        with mido.open_output(out_name) as outport:
            outport.send(mido.Message("note_on", note=int(note), velocity=int(velocity)))
        return True

    def apply_config(self, device_name, buttons):
        out_name = self.resolve_output_name([device_name])
        if not out_name:
            return False
        with mido.open_output(out_name) as outport:
            for note in range(128):
                outport.send(mido.Message("note_on", note=note, velocity=0))
            for note, payload in buttons.items():
                color = MidiConfigManager.normalize_color_value(payload.get("color", 63))
                outport.send(mido.Message("note_on", note=int(note), velocity=int(color)))
        return True


class MidiReaderRunner:
    def __init__(self, config_path, message_queue, operation_queue=None, operation_commands=None, log_fn=None):
        self.config_path = config_path
        self.message_queue = message_queue
        self.operation_queue = operation_queue
        self.operation_commands = operation_commands or set()
        self.log_fn = log_fn or (lambda msg: None)
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop_event.set()

    def _run(self):
        inport = None
        outport = None
        try:
            if not self.config_path:
                self.log_fn("No MIDI config selected.")
                return

            device_name_csv, buttons = load_midi_config(self.config_path)
            if not device_name_csv:
                self.log_fn("No device specified in JSON.")
                return

            inport, outport = open_midi_device(device_name_csv)
            if not inport:
                self.log_fn("MIDI device not available.")
                return

            turn_off_all_leds(outport)
            turn_on_leds(outport, buttons)

            pressed_notes = set()
            while not self._stop_event.is_set():
                for msg in inport.iter_pending():
                    if msg.type == "note_on" and msg.velocity > 0:
                        note = msg.note
                        if str(note) in buttons and note not in pressed_notes:
                            tag = buttons[str(note)]["tag"]
                            btn_type = buttons[str(note)]["type"]
                            if btn_type == "Operation":
                                if tag in self.operation_commands and self.operation_queue is not None:
                                    self.operation_queue.put(tag)
                            else:
                                self.message_queue.put((btn_type, tag))
                            pressed_notes.add(note)
                    elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                        note = msg.note
                        if note in pressed_notes:
                            pressed_notes.remove(note)

                time.sleep(0.01)
        except Exception as exc:
            self.log_fn(f"MIDI reader error: {exc}")
        finally:
            try:
                if inport:
                    inport.close()
            except Exception:
                pass
            try:
                if outport:
                    outport.close()
            except Exception:
                pass

# ---------------- FUNCTIONS ----------------
def select_midi_config():
    if not os.path.exists(MIDI_CONFIG_FOLDER):
        print(f"No folder '{MIDI_CONFIG_FOLDER}' found.")
        return None

    files = [f for f in os.listdir(MIDI_CONFIG_FOLDER) if f.endswith(".json")]
    if not files:
        print("No MIDI configuration files found.")
        return None

    print("Available MIDI configuration files:")
    for i, f in enumerate(files):
        print(f"{i}: {f}")

    while True:
        try:
            choice = int(input("Select a file to load: "))
            json_file = os.path.join(MIDI_CONFIG_FOLDER, files[choice])
            return json_file
        except (ValueError, IndexError):
            print("Invalid choice. Try again.")


def load_midi_config(json_file):
    data = MidiConfigManager.load(json_file)
    device_name = data.get("device_name")
    buttons = data.get("buttons", {})
    return device_name, buttons


def open_midi_device(device_name_csv):
    available_inputs = mido.get_input_names()
    available_outputs = mido.get_output_names()

    if device_name_csv in available_inputs:
        in_name = device_name_csv
    else:
        print(f"Input device '{device_name_csv}' not found.")
        print("Available MIDI input devices:")
        for name in available_inputs:
            print(f" - {name}")
        return None, None

    if device_name_csv in available_outputs:
        out_name = device_name_csv
    else:
        prefix = device_name_csv.rsplit(" ", 1)[0]
        out_name = None
        for name in available_outputs:
            if name.startswith(prefix):
                out_name = name
                print(f"Output device '{device_name_csv}' not found. Using '{out_name}' instead.")
                break
        if not out_name:
            print(f"Could not find any matching output device for '{device_name_csv}'.")
            print("Available MIDI output devices:")
            for name in available_outputs:
                print(f" - {name}")
            return None, None

    try:
        inport = mido.open_input(in_name)
        outport = mido.open_output(out_name)
        return inport, outport
    except IOError as e:
        print(f"Error opening MIDI devices: {e}")
        return None, None


def turn_on_leds(outport, buttons):
    for note, payload in buttons.items():
        color = MidiConfigManager.normalize_color_value(payload.get("color", 63))
        msg = mido.Message("note_on", note=int(note), velocity=int(color))
        outport.send(msg)
        time.sleep(0.01)
    print(f"Turned on LEDs for {len(buttons)} configured buttons.")


def turn_off_all_leds(outport):
    for note in range(128):
        msg = mido.Message("note_on", note=note, velocity=0)
        outport.send(msg)
        time.sleep(0.005)
    print("All LEDs turned off.")


# ---------------- MAIN ----------------
def main():
    json_file = select_midi_config()
    if not json_file:
        print("No MIDI config selected. Exiting.")
        return

    device_name_csv, buttons = load_midi_config(json_file)
    if not device_name_csv:
        print("No device specified in JSON. Exiting.")
        return

    inport, outport = open_midi_device(device_name_csv)
    if not inport:
        return

    turn_off_all_leds(outport)
    turn_on_leds(outport, buttons)

    print("Listening for button presses... Press Ctrl+C to exit.")

    pressed_notes = set()

    try:
        while True:
            for msg in inport.iter_pending():
                if msg.type == "note_on" and msg.velocity > 0:
                    note = msg.note
                    if str(note) in buttons and note not in pressed_notes:
                        tag = buttons[str(note)]["tag"]
                        btn_type = buttons[str(note)]["type"]
                        print(f"Button pressed: Tag='{tag}', Type='{btn_type}'")
                        pressed_notes.add(note)
                elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                    note = msg.note
                    if note in pressed_notes:
                        pressed_notes.remove(note)

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("Exiting...")
        outport.close()
        inport.close()


if __name__ == "__main__":
    main()
