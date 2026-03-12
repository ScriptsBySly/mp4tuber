import sys
import os
import json
import mido
import keyboard

ALLOWED_TYPES = ["Emotes", "AFK", "Operation"]


def list_input_devices():
    return mido.get_input_names()


def select_device_cli(preselected=None):
    print("Available MIDI input devices:")
    input_names = list_input_devices()
    for i, name in enumerate(input_names):
        print(f"{i}: {name}")

    if preselected and preselected in input_names:
        print(f"Using preselected device: {preselected}")
        return preselected

    while True:
        try:
            selection = int(input("Select a MIDI device by number: "))
            device_name = input_names[selection]
            return device_name
        except (ValueError, IndexError):
            print("Invalid selection. Try again.")


def list_existing_files(folder_name):
    if not os.path.isdir(folder_name):
        return []
    return [f for f in os.listdir(folder_name) if f.endswith(".json")]


def create_new_file(device_name, folder_name, existing_files):
    base = device_name.replace(" ", "_")
    suffixes = [
        int(f.split("_")[-1].split(".")[0])
        for f in existing_files
        if "_" in f and f.split("_")[-1].split(".")[0].isdigit()
    ]
    next_suffix = max(suffixes, default=0) + 1
    json_file_name = os.path.join(folder_name, f"{base}_{next_suffix}.json")
    data = {
        "schema_version": 1,
        "device_name": device_name,
        "buttons": {},
    }
    with open(json_file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return json_file_name


def choose_or_create_file_cli(device_name, folder_name):
    os.makedirs(folder_name, exist_ok=True)
    existing_files = list_existing_files(folder_name)

    if existing_files:
        print("Existing files:")
        for i, f in enumerate(existing_files):
            print(f"{i}: {f}")
        print(f"{len(existing_files)}: Create a new file")

        while True:
            try:
                choice = int(input("Select a file to edit or create new: "))
                if choice == len(existing_files):
                    return create_new_file(device_name, folder_name, existing_files)
                return os.path.join(folder_name, existing_files[choice])
            except (ValueError, IndexError):
                print("Invalid selection. Try again.")
    return create_new_file(device_name, folder_name, existing_files)


def load_config(json_file_name):
    if not os.path.exists(json_file_name):
        return None, {}

    with open(json_file_name, "r", encoding="utf-8") as f:
        data = json.load(f)

    device_name = data.get("device_name")
    buttons_raw = data.get("buttons", {})
    buttons = {}

    if isinstance(buttons_raw, list):
        for item in buttons_raw:
            try:
                note = int(item["note"])
                buttons[note] = {"tag": item["tag"], "type": item["type"]}
            except Exception:
                continue
    elif isinstance(buttons_raw, dict):
        for note_str, payload in buttons_raw.items():
            try:
                note = int(note_str)
                buttons[note] = {"tag": payload["tag"], "type": payload["type"]}
            except Exception:
                continue

    return device_name, buttons


def save_config(json_file_name, device_name, buttons):
    data = {
        "schema_version": 1,
        "device_name": device_name,
        "buttons": {str(note): payload for note, payload in buttons.items()},
    }
    with open(json_file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def run_config_loop(device_name, json_file_name, buttons):
    pressed_notes = set()
    print("Press ESC to finish configuring buttons.")

    with mido.open_input(device_name) as inport:
        while True:
            if keyboard.is_pressed("esc"):
                print("ESC pressed. Exiting.")
                break

            for msg in inport.iter_pending():
                if msg.type == "note_on" and msg.velocity == 127:
                    note = msg.note

                    if note in buttons:
                        print(
                            f"Button {note} is already configured with tag '{buttons[note]['tag']}' "
                            f"and type '{buttons[note]['type']}'"
                        )
                        continue

                    if note in pressed_notes:
                        continue

                    tag = input(f"Enter tag for button {note}: ")

                    while True:
                        btn_type = input(
                            f"Select type for button {note} ('Emotes', 'AFK', or 'Operation'): "
                        ).strip()
                        if btn_type in ALLOWED_TYPES:
                            break
                        print("Invalid type. Please enter 'Emotes', 'AFK', or 'Operation'.")

                    buttons[note] = {"tag": tag, "type": btn_type}
                    save_config(json_file_name, device_name, buttons)

                    pressed_notes.add(note)
                    print(f"Button {note} saved with tag '{tag}' and type '{btn_type}'")


def main():
    preselected = None
    if len(sys.argv) > 1:
        preselected = " ".join(sys.argv[1:])
    device_name = select_device_cli(preselected=preselected)

    folder_name = "midi_configs"
    json_file_name = choose_or_create_file_cli(device_name, folder_name)
    print(f"Using file: {json_file_name}")

    device_name, buttons = load_config(json_file_name)
    if not device_name:
        device_name = select_device_cli(preselected=preselected)
        save_config(json_file_name, device_name, buttons)

    run_config_loop(device_name, json_file_name, buttons)


if __name__ == "__main__":
    main()
