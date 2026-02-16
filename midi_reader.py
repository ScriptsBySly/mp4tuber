import os
import csv
import socket
import mido
import time

# ---------------- CONFIG ----------------
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 5000

MIDI_CONFIG_FOLDER = "midi_configs"

# ---------------- FUNCTIONS ----------------
def select_midi_config():
    """Select a CSV config file from midi_configs folder."""
    if not os.path.exists(MIDI_CONFIG_FOLDER):
        print(f"No folder '{MIDI_CONFIG_FOLDER}' found.")
        return None

    files = [f for f in os.listdir(MIDI_CONFIG_FOLDER) if f.endswith(".csv")]
    if not files:
        print("No MIDI configuration files found.")
        return None

    print("Available MIDI configuration files:")
    for i, f in enumerate(files):
        print(f"{i}: {f}")

    while True:
        try:
            choice = int(input("Select a file to load: "))
            csv_file = os.path.join(MIDI_CONFIG_FOLDER, files[choice])
            return csv_file
        except (ValueError, IndexError):
            print("Invalid choice. Try again.")


def load_midi_config(csv_file):
    """Load device name and button mappings from CSV file."""
    buttons = {}
    device_name = None

    if not os.path.exists(csv_file):
        return None, buttons

    with open(csv_file, 'r', newline='') as f:
        reader = csv.reader(f)
        rows = list(reader)
        if len(rows) < 2:
            print("CSV file is empty or malformed.")
            return None, buttons

        # First line is device name
        device_name = rows[0][0]

        # Second line is header, skip
        for row in rows[2:]:
            note = int(row[0])
            tag = row[1]
            btn_type = row[2]
            buttons[note] = {'tag': tag, 'type': btn_type}

    return device_name, buttons


def open_midi_device(device_name_csv):
    """Open the MIDI input and output device. Allows different input/output indexes if needed."""
    available_inputs = mido.get_input_names()
    available_outputs = mido.get_output_names()
    
    # Open input: must match CSV exactly
    if device_name_csv in available_inputs:
        in_name = device_name_csv
    else:
        print(f"Input device '{device_name_csv}' not found.")
        print("Available MIDI input devices:")
        for name in available_inputs:
            print(f" - {name}")
        return None, None

    # Open output: look for exact match, else use first device with same prefix
    if device_name_csv in available_outputs:
        out_name = device_name_csv
    else:
        prefix = device_name_csv.rsplit(' ', 1)[0]
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
    """Turn on green LEDs for all configured buttons (velocity=127)."""
    for note in buttons:
        msg = mido.Message('note_on', note=note, velocity=127)
        outport.send(msg)
        time.sleep(0.01)
    print(f"Turned on LEDs for {len(buttons)} configured buttons.")

def turn_off_all_leds(outport):
    """Turn off all LEDs on the MIDI device (velocity=0)."""
    for note in range(128):  # MIDI notes range from 0 to 127
        msg = mido.Message('note_on', note=note, velocity=0)
        outport.send(msg)
        time.sleep(0.005)  # small delay to ensure MIDI device receives messages
    print("All LEDs turned off.")

# ---------------- MAIN ----------------
def main():
    # Connect to server
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((SERVER_HOST, SERVER_PORT))
    print(f"Connected to server at {SERVER_HOST}:{SERVER_PORT}")

    # Select MIDI config
    csv_file = select_midi_config()
    if not csv_file:
        print("No MIDI config selected. Exiting.")
        return

    device_name_csv, buttons = load_midi_config(csv_file)
    if not device_name_csv:
        print("No device specified in CSV. Exiting.")
        return

    # Open MIDI device using Option 2 logic
    inport, outport = open_midi_device(device_name_csv)
    if not inport:
        return

    # Reset board first
    turn_off_all_leds(outport)

    # Turn on LEDs for configured buttons
    turn_on_leds(outport, buttons) 

    print("Listening for button presses... Press Ctrl+C to exit.")

    pressed_notes = set()  # simple debounce for current session

    try:
        while True:
            for msg in inport.iter_pending():
                if msg.type == 'note_on' and msg.velocity > 0:
                    note = msg.note
                    if note in buttons and note not in pressed_notes:
                        tag = buttons[note]['tag']
                        btn_type = buttons[note]['type']

                        # Print info locally
                        print(f"Button pressed: Tag='{tag}', Type='{btn_type}'")

                        # Send to server
                        message = f"{btn_type},{tag}"
                        client.sendall(message.encode('utf-8'))

                        # Mark as pressed for this session
                        pressed_notes.add(note)
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    # Remove from pressed_notes so next press can be detected
                    note = msg.note
                    if note in pressed_notes:
                        pressed_notes.remove(note)

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("Exiting...")
        client.close()
        outport.close()
        inport.close()


if __name__ == "__main__":
    main()
