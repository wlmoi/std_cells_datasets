import matplotlib.pyplot as plt
import matplotlib.patches as patches
import random
import os # Import modul os untuk mendapatkan path direktori dan menangani file

## magReader.py
## run in terminal
## 

# python d:/std_cells_datasets/std_cells_datasets/magReader.py

# Cache untuk menyimpan data sel yang sudah diurai agar tidak mengurai ulang
_parsed_cell_cache = {}

def parse_mag_data(file_path, current_dir=None):
    """
    Mengurai konten data .mag dari file dan mengembalikan struktur data yang terorganisir.
    Mendukung penguraian sel yang diinstansiasi secara rekursif.
    """
    if file_path in _parsed_cell_cache:
        return _parsed_cell_cache[file_path]

    # Menentukan direktori saat ini jika tidak disediakan (untuk panggilan rekursif)
    if current_dir is None:
        current_dir = os.path.dirname(file_path)
    
    # Membangun path lengkap jika file_path bukan path absolut
    if not os.path.isabs(file_path):
        full_file_path = os.path.join(current_dir, file_path)
    else:
        full_file_path = file_path

    # Menyesuaikan current_dir untuk file yang sedang diurai
    current_dir_for_subcells = os.path.dirname(full_file_path)

    try:
        with open(full_file_path, 'r') as file:
            mag_content = file.read()
    except FileNotFoundError:
        print(f"Warning: Referenced file '{full_file_path}' not found. Skipping instance.")
        return None
    except Exception as e:
        print(f"Error reading file '{full_file_path}': {e}. Skipping instance.")
        return None

    parsed_data = {
        "header": {},
        "layers": {},
        "instances": [] # Menambahkan list untuk menyimpan instans sel
    }
    current_layer = None
    lines = mag_content.strip().split('\n')

    # Variabel sementara untuk menyimpan data instance yang sedang diurai
    current_instance = None 

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("magic"):
            parts = line.split(" ", 2)
            if len(parts) > 1:
                parsed_data["header"]["file_type"] = parts[0]
                parsed_data["header"]["magic_version"] = parts[1]
                if len(parts) > 2:
                    parsed_data["header"]["extra"] = parts[2]
        elif line.startswith("tech"):
            parsed_data["header"]["tech"] = line.split(" ", 1)[1]
        elif line.startswith("timestamp"):
            if current_instance: # Ini adalah timestamp untuk instance
                try:
                    current_instance["timestamp"] = int(line.split(" ", 1)[1])
                except ValueError:
                    pass
            else: # Ini adalah timestamp untuk sel utama
                try:
                    parsed_data["header"]["timestamp"] = int(line.split(" ", 1)[1])
                except ValueError:
                    pass
        elif line.startswith("<<") and line.endswith(">>"):
            current_layer = line.strip("<<>> ").strip()
            if current_layer not in parsed_data["layers"]:
                parsed_data["layers"][current_layer] = {
                    "rects": [],
                    "labels": []
                }
        elif line.startswith("rect"):
            if current_layer:
                parts = line.split()
                if len(parts) == 5:
                    try:
                        x1, y1, x2, y2 = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                        parsed_data["layers"][current_layer]["rects"].append({
                            "x1": x1, "y1": y1, "x2": x2, "y2": y2
                        })
                    except ValueError:
                        pass
        elif line.startswith("rlabel"):
            if current_layer:
                parts = line.split(" ", 7)
                if len(parts) >= 8:
                    try:
                        label_layer = parts[1]
                        x1, y1, x2, y2 = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
                        rotation = int(parts[6])
                        label_text = parts[7]
                        parsed_data["layers"][current_layer]["labels"].append({
                            "layer": label_layer,
                            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                            "rotation": rotation,
                            "text": label_text
                        })
                    except (ValueError, IndexError):
                        pass
        elif line.startswith("use "):
            # Selesai dengan instance sebelumnya jika ada
            if current_instance:
                parsed_data["instances"].append(current_instance)
                current_instance = None # Reset for next instance

            parts = line.split()
            if len(parts) >= 3:
                cell_type = parts[1]
                instance_name = parts[2]
                
                # Default path is cell_type.mag in the current directory
                sub_file_name = f"{cell_type}.mag"
                
                # Check if an explicit path is provided (e.g., /foss/designs/eda/nand)
                if len(parts) > 3 and parts[3].startswith('/'): # Heuristic for absolute path
                    sub_file_path = parts[3]
                else:
                    sub_file_path = os.path.join(current_dir_for_subcells, sub_file_name)

                # Recursively parse the sub-cell
                parsed_sub_cell_content = parse_mag_data(sub_file_path, current_dir_for_subcells)
                
                if parsed_sub_cell_content:
                    current_instance = {
                        "cell_type": cell_type,
                        "instance_name": instance_name,
                        "file_path": sub_file_path,
                        "parsed_content": parsed_sub_cell_content,
                        "transform": [1, 0, 0, 0, 1, 0], # Default identity transform
                        "box": [0, 0, 0, 0], # Default bounding box
                        "timestamp": None
                    }
                else:
                    current_instance = None # If sub-cell not found, don't create instance
            
        elif line.startswith("transform ") and current_instance:
            # Apply transform to the current instance
            try:
                transform_values = [float(x) for x in line.split()[1:]]
                if len(transform_values) == 6:
                    current_instance["transform"] = transform_values
            except ValueError:
                pass
        elif line.startswith("box ") and current_instance:
            # Apply bounding box to the current instance
            try:
                box_values = [int(x) for x in line.split()[1:]]
                if len(box_values) == 4:
                    current_instance["box"] = box_values
            except ValueError:
                pass
        elif line == "<< end >>":
            # Add the last instance if it exists before ending
            if current_instance:
                parsed_data["instances"].append(current_instance)
                current_instance = None
            break

    # Add the last instance if it exists (e.g., if file ends directly after a 'use' block)
    if current_instance:
        parsed_data["instances"].append(current_instance)

    _parsed_cell_cache[full_file_path] = parsed_data
    return parsed_data

def visualize_layout(parsed_data, file_name, title_prefix="Layout Visualization", layer_colors=None):
    """
    Memvisualisasikan data layout yang diurai menggunakan matplotlib.
    Juga menampilkan informasi header di plot, dan menggambar sel instansiasi.
    """
    fig, ax = plt.subplots(1, figsize=(12, 10)) # Ukuran figur diperbesar sedikit

    min_x, max_x, min_y, max_y = float('inf'), float('-inf'), float('inf'), float('-inf')

    # Inisialisasi atau gunakan warna lapisan dari panggilan rekursif
    if layer_colors is None:
        layer_colors = {}
    
    # Generate random colors for layers
    def get_random_color():
        r = random.random()
        g = random.random()
        b = random.random()
        return (r, g, b)

    def _apply_transform(x, y, transform_matrix):
        """Menerapkan transformasi affine ke koordinat (x, y)."""
        # Transformasi Magic adalah:
        # A B C
        # D E F
        # x' = Ax + By + C
        # y' = Dx + Ey + F
        A, B, C, D, E, F = transform_matrix
        new_x = A * x + B * y + C
        new_y = D * x + E * y + F
        return new_x, new_y

    def _draw_elements(data_to_draw, current_transform=[1, 0, 0, 0, 1, 0]):
        nonlocal min_x, max_x, min_y, max_y # Akses variabel dari scope luar

        for layer_name, layer_data in data_to_draw["layers"].items():
            if layer_name == "end": # Skip the 'end' layer
                continue

            if layer_name not in layer_colors:
                layer_colors[layer_name] = get_random_color()
            
            color = layer_colors[layer_name]

            for rect in layer_data["rects"]:
                # Mengubah 4 sudut persegi panjang
                corners = [
                    (rect["x1"], rect["y1"]),
                    (rect["x2"], rect["y1"]),
                    (rect["x1"], rect["y2"]),
                    (rect["x2"], rect["y2"])
                ]
                transformed_corners = [_apply_transform(cx, cy, current_transform) for cx, cy in corners]

                # Mencari min/max x dan y dari sudut yang ditransformasi
                tx_coords = [c[0] for c in transformed_corners]
                ty_coords = [c[1] for c in transformed_corners]

                transformed_x1 = min(tx_coords)
                transformed_y1 = min(ty_coords)
                transformed_x2 = max(tx_coords)
                transformed_y2 = max(ty_coords)

                width = transformed_x2 - transformed_x1
                height = transformed_y2 - transformed_y1

                # Perbarui batas plot
                min_x = min(min_x, transformed_x1)
                max_x = max(max_x, transformed_x2)
                min_y = min(min_y, transformed_y1)
                max_y = max(max_y, transformed_y2)

                rect_patch = patches.Rectangle((transformed_x1, transformed_y1), width, height,
                                               linewidth=1, edgecolor='black', facecolor=color, alpha=0.7,
                                               label=layer_name if layer_name not in ax.get_legend_handles_labels()[1] else "")
                ax.add_patch(rect_patch)

            for label in layer_data["labels"]:
                # Transformasi titik tengah label
                center_x = (label["x1"] + label["x2"]) / 2
                center_y = (label["y1"] + label["y2"]) / 2
                transformed_center_x, transformed_center_y = _apply_transform(center_x, center_y, current_transform)
                
                ax.text(transformed_center_x, transformed_center_y, label["text"],
                        color='blue', fontsize=8, ha='center', va='center',
                        bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', boxstyle='round,pad=0.2'))

    # Gambar sel utama
    _draw_elements(parsed_data)

    # Gambar semua instans yang dienkapsulasi
    for instance in parsed_data.get("instances", []):
        if instance.get("parsed_content"):
            # Kombinasikan transformasi (jika ada hierarki bertingkat)
            # Untuk saat ini, kita hanya menerapkan transformasi instance
            _draw_elements(instance["parsed_content"], instance["transform"])
            # Tambahkan label instance
            if instance.get("box"): # Gunakan bounding box jika ada
                bx1, by1, bx2, by2 = instance["box"]
                t_bx1, t_by1 = _apply_transform(bx1, by1, instance["transform"])
                t_bx2, t_by2 = _apply_transform(bx2, by2, instance["transform"])
                inst_center_x = (t_bx1 + t_bx2) / 2
                inst_center_y = (t_by1 + t_by2) / 2
            else: # Fallback ke titik tengah jika tidak ada bounding box
                inst_center_x, inst_center_y = _apply_transform(0, 0, instance["transform"]) # Menganggap 0,0 sebagai referensi

            ax.text(inst_center_x, inst_center_y, instance["instance_name"],
                    color='red', fontsize=10, ha='center', va='center', fontweight='bold',
                    bbox=dict(facecolor='yellow', alpha=0.6, edgecolor='black', boxstyle='round,pad=0.3'))


    # Mengatur batas plot sedikit lebih luas dari desain
    padding = 20
    ax.set_xlim(min_x - padding, max_x + padding)
    ax.set_ylim(min_y - padding, max_y + padding)

    ax.set_aspect('equal', adjustable='box') # Memastikan skala x dan y sama
    ax.set_xlabel("X Coordinate")
    ax.set_ylabel("Y Coordinate")
    
    # --- Set title to include the exact file name entered by the user ---
    ax.set_title(f"{title_prefix}: {file_name}") # Judul langsung dengan nama file yang diinput

    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5)) # Legenda di luar plot

    # --- Tambahkan informasi header ke plot ---
    header_text = f"Tech: {parsed_data['header'].get('tech', 'N/A')}\n" \
                  f"Timestamp: {parsed_data['header'].get('timestamp', 'N/A')}"
    
    # --- Tempatkan teks di sudut kanan atas plot ---
    ax.text(1.02, 0.98, header_text, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', bbox=dict(boxstyle='round,pad=0.3', fc='wheat', alpha=0.7))

    plt.tight_layout(rect=[0, 0, 0.9, 1]) # Sesuaikan layout untuk memberi ruang pada legenda dan teks
    plt.show() # Menampilkan plot

# --- Fungsi untuk mencetak detail ke konsol (seperti .txt) ---
def print_parsed_details(parsed_data, indent=0, file_name=""):
    prefix = "  " * indent
    if indent == 0:
        print(f"--- Details for {file_name} ---")

    print(f"{prefix}Header Information:")
    for key, value in parsed_data["header"].items():
        print(f"{prefix}  {key}: {value}")

    print(f"{prefix}Layer Information:")
    for layer_name, layer_data in parsed_data["layers"].items():
        # Jangan mencetak layer 'end' karena itu hanya penanda file
        if layer_name == "end":
            continue

        print(f"{prefix}  Layer: {layer_name}")
        if layer_data["rects"]:
            print(f"{prefix}    Rectangles:")
            for rect in layer_data["rects"]:
                width = abs(rect["x2"] - rect["x1"])
                height = abs(rect["y2"] - rect["y1"])
                print(f"{prefix}      x1: {rect['x1']}, y1: {rect['y1']}, x2: {rect['x2']}, y2: {rect['y2']}, Width: {width}, Height: {height}")
        if layer_data["labels"]:
            print(f"{prefix}    Labels:")
            for label in layer_data["labels"]:
                print(f"{prefix}      Text: '{label['text']}' at ({label['x1']}, {label['y1']}) to ({label['x2']}, {label['y2']}), Layer: {label['layer']}, Rotation: {label['rotation']}")
    
    if parsed_data.get("instances"):
        print(f"{prefix}Instances:")
        for instance in parsed_data["instances"]:
            print(f"{prefix}  Instance: {instance['instance_name']} (Type: {instance['cell_type']})")
            print(f"{prefix}    File: {instance['file_path']}")
            print(f"{prefix}    Timestamp: {instance['timestamp']}")
            print(f"{prefix}    Transform: {instance['transform']}")
            print(f"{prefix}    Box: {instance['box']}")
            if instance.get("parsed_content"):
                # Rekursif panggil untuk detail instance
                print(f"{prefix}    --- Sub-cell Details ({instance['cell_type']}.mag) ---")
                print_parsed_details(instance["parsed_content"], indent + 2)
                print(f"{prefix}    --- End Sub-cell Details ---")
            else:
                print(f"{prefix}    (Sub-cell content not available or file not found)")


# --- Input file data ---
file_path_input = input("Enter your top-level .mag file name (e.g., top_level.mag): ")

# Mendapatkan direktori dari file input untuk pencarian relatif
initial_dir = os.path.dirname(os.path.abspath(file_path_input))

try:
    # Memanggil parse_mag_data dengan path lengkap dan direktori awal
    parsed_mag = parse_mag_data(file_path_input, current_dir=initial_dir)

    if parsed_mag:
        # Cetak detail ke konsol terlebih dahulu
        print_parsed_details(parsed_mag, file_name=file_path_input)

        # Kemudian tampilkan visualisasi, meneruskan nama file
        visualize_layout(parsed_mag, file_name=file_path_input, title_prefix="Layout Design")
    else:
        print(f"Failed to parse the main file: '{file_path_input}'.")

except FileNotFoundError:
    print(f"Error: File '{file_path_input}' not found. Please make sure the file path is correct and in the same directory, or provide the full path.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

