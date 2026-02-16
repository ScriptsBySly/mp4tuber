import mido
import os
import csv
import keyboard

# ------------------------ Device Selection ------------------------
print("Available MIDI input devices:")
input_names = mido.get_input_names()
for i, name in enumerate(input_names):
    print(f"{i}: {name}")

while True:
    try:
        selection = int(input("Select a MIDI device by number: "))
        device_name = input_names[selection]
        break
    except (ValueError, IndexError):
        print("Invalid selection. Try again.")

# ------------------------ File Handling ------------------------
# Folder for MIDI files
folder_name = "midi_configs"
os.makedirs(folder_name, exist_ok=True)

# List existing CSV files
existing_files = [f for f in os.listdir(folder_name) if f.endswith(".csv")]
if existing_files:
    print("Existing files:")
    for i, f in enumerate(existing_files):
        print(f"{i}: {f}")
    print(f"{len(existing_files)}: Create a new file")

    while True:
        try:
            choice = int(input("Select a file to edit or create new: "))
            if choice == len(existing_files):
                # Determine next numeric suffix
                base = device_name.replace(" ", "_")
                suffixes = [int(f.split("_")[-1].split(".")[0]) for f in existing_files if "_" in f and f.split("_")[-1].split(".")[0].isdigit()]
                next_suffix = max(suffixes, default=0) + 1
                csv_file_name = os.path.join(folder_name, f"{base}_{next_suffix}.csv")
                # Create new file with device name as first line and header
                with open(csv_file_name, 'w', newline='') as csv_file:
                    csv_file.write(device_name + "\n")  # First line: device name
                    writer = csv.DictWriter(csv_file, fieldnames=['note', 'tag', 'type'])
                    writer.writeheader()
                break
            else:
                csv_file_name = os.path.join(folder_name, existing_files[choice])
                break
        except (ValueError, IndexError):
            print("Invalid selection. Try again.")
else:
    # No existing files, create first
    base = device_name.replace(" ", "_")
    csv_file_name = os.path.join(folder_name, f"{base}_1.csv")
    with open(csv_file_name, 'w', newline='') as csv_file:
        csv_file.write(device_name + "\n")  # First line: device name
        writer = csv.DictWriter(csv_file, fieldnames=['note', 'tag', 'type'])
        writer.writeheader()

print(f"Using file: {csv_file_name}")

# ------------------------ Load Existing Entries ------------------------
entries = {}
if os.path.exists(csv_file_name):
    with open(csv_file_name, 'r', newline='') as f:
        lines = f.readlines()
        # Skip first line (device name) and header
        for row in lines[2:]:
            row = row.strip()
            if not row:
                continue
            note_str, tag, btn_type = row.split(',')
            note = int(note_str)
            entries[note] = {'tag': tag, 'type': btn_type}

pressed_notes = set()  # Debounce for current session

# ------------------------ MIDI Listening ------------------------
print("Press ESC to finish configuring buttons.")

with mido.open_input(device_name) as inport:
    while True:
        # Check for ESC key to finish
        if keyboard.is_pressed('esc'):
            print("ESC pressed. Exiting.")
            break

        for msg in inport.iter_pending():
            # Only consider Note On messages with velocity 127
            if msg.type == 'note_on' and msg.velocity == 127:
                note = msg.note

                # Already configured in file
                if note in entries:
                    print(f"Button {note} is already configured with tag '{entries[note]['tag']}' and type '{entries[note]['type']}'")
                    continue

                # Already pressed in this session
                if note in pressed_notes:
                    continue

                tag = input(f"Enter tag for button {note}: ")

                # Select button type
                while True:
                    btn_type = input(f"Select type for button {note} ('Emotes' or 'AFK'): ").strip()
                    if btn_type in ['Emotes', 'AFK']:
                        break
                    else:
                        print("Invalid type. Please enter 'Emotes' or 'AFK'.")

                # Save to CSV
                with open(csv_file_name, 'a', newline='') as csv_file:
                    writer = csv.DictWriter(csv_file, fieldnames=['note', 'tag', 'type'])
                    writer.writerow({'note': note, 'tag': tag, 'type': btn_type})

                # Update in-memory dict and pressed notes
                entries[note] = {'tag': tag, 'type': btn_type}
                pressed_notes.add(note)
                print(f"Button {note} saved with tag '{tag}' and type '{btn_type}'")
