import sys
import os
import json
import mido
import keyboard

ALLOWED_TYPES = ["Emotes", "AFK", "Operation"]
LAUNCHPAD_S_COLOR_VALUES = [12, 13, 14, 15, 28, 29, 30, 31, 44, 45, 46, 47, 60, 61, 62, 63]
DEFAULT_COLOR = 63


class MidiConfigManager:
    @staticmethod
    def new_config(device_name=""):
        return {
            "schema_version": 1,
            "device_name": device_name,
            "buttons": {},
        }

    @staticmethod
    def load(path):
        if not os.path.exists(path):
            return MidiConfigManager.new_config()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = MidiConfigManager.new_config()
        if "schema_version" not in data:
            data["schema_version"] = 1
        if "device_name" not in data:
            data["device_name"] = ""
        if "buttons" not in data:
            data["buttons"] = {}
        if isinstance(data.get("buttons"), list):
            buttons = {}
            for item in data["buttons"]:
                try:
                    note = int(item.get("note"))
                    buttons[str(note)] = {
                        "tag": item.get("tag", ""),
                        "type": item.get("type", ""),
                        "color": MidiConfigManager.normalize_color_value(item.get("color", DEFAULT_COLOR)),
                    }
                except Exception:
                    continue
            data["buttons"] = buttons
        return data

    @staticmethod
    def save(path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def list_existing_files(folder_name):
        if not os.path.isdir(folder_name):
            return []
        return [f for f in os.listdir(folder_name) if f.endswith(".json")]

    @staticmethod
    def create_new_file(device_name, folder_name, existing_files):
        base = device_name.replace(" ", "_") if device_name else "midi"
        suffixes = [
            int(f.split("_")[-1].split(".")[0])
            for f in existing_files
            if "_" in f and f.split("_")[-1].split(".")[0].isdigit()
        ]
        next_suffix = max(suffixes, default=0) + 1
        json_file_name = os.path.join(folder_name, f"{base}_{next_suffix}.json")
        data = MidiConfigManager.new_config(device_name)
        MidiConfigManager.save(json_file_name, data)
        return json_file_name

    @staticmethod
    def add_button(data, note, tag="", btn_type="", color=DEFAULT_COLOR):
        buttons = data.get("buttons", {})
        buttons[str(note)] = {
            "tag": tag,
            "type": btn_type,
            "color": MidiConfigManager.normalize_color_value(color),
        }
        data["buttons"] = buttons
        return data

    @staticmethod
    def normalize_color_value(color):
        try:
            color = int(color)
        except Exception:
            return LAUNCHPAD_S_COLOR_VALUES[0]
        if color in LAUNCHPAD_S_COLOR_VALUES:
            return color
        closest = min(LAUNCHPAD_S_COLOR_VALUES, key=lambda v: abs(v - color))
        return closest

    @staticmethod
    def velocity_to_color_index(color):
        try:
            color = int(color)
        except Exception:
            return 0
        if color in LAUNCHPAD_S_COLOR_VALUES:
            return LAUNCHPAD_S_COLOR_VALUES.index(color)
        closest = min(LAUNCHPAD_S_COLOR_VALUES, key=lambda v: abs(v - color))
        return LAUNCHPAD_S_COLOR_VALUES.index(closest)

    @staticmethod
    def color_index_to_velocity(color_index):
        try:
            color_index = int(color_index)
        except Exception:
            color_index = 0
        color_index = max(0, min(len(LAUNCHPAD_S_COLOR_VALUES) - 1, color_index))
        return LAUNCHPAD_S_COLOR_VALUES[color_index]


# ---- CLI ----

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


def choose_or_create_file_cli(device_name, folder_name):
    os.makedirs(folder_name, exist_ok=True)
    existing_files = MidiConfigManager.list_existing_files(folder_name)

    if existing_files:
        print("Existing files:")
        for i, f in enumerate(existing_files):
            print(f"{i}: {f}")
        print(f"{len(existing_files)}: Create a new file")

        while True:
            try:
                choice = int(input("Select a file to edit or create new: "))
                if choice == len(existing_files):
                    return MidiConfigManager.create_new_file(device_name, folder_name, existing_files)
                return os.path.join(folder_name, existing_files[choice])
            except (ValueError, IndexError):
                print("Invalid selection. Try again.")
    return MidiConfigManager.create_new_file(device_name, folder_name, existing_files)


def run_config_loop(device_name, json_file_name, data):
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

                    if str(note) in data.get("buttons", {}):
                        existing = data["buttons"][str(note)]
                        print(
                            f"Button {note} is already configured with tag '{existing.get('tag','')}' "
                            f"and type '{existing.get('type','')}'"
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

                    MidiConfigManager.add_button(
                        data,
                        note,
                        tag=tag,
                        btn_type=btn_type,
                        color=DEFAULT_COLOR,
                    )
                    MidiConfigManager.save(json_file_name, data)

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

    data = MidiConfigManager.load(json_file_name)
    if not data.get("device_name"):
        data["device_name"] = device_name
        MidiConfigManager.save(json_file_name, data)

    run_config_loop(device_name, json_file_name, data)


if __name__ == "__main__":
    main()
