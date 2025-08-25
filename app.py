# ==============================================================================
# 📦 Aplikasi Pengepakan Kontainer 3D Interaktif
#
# Deskripsi:
# Aplikasi web ini memungkinkan pengguna untuk mengonfigurasi ukuran kontainer dan
# daftar barang, lalu menjalankan algoritma pengepakan untuk menempatkan barang
# secara efisien. Hasilnya ditampilkan dalam visualisasi 3D yang interaktif
# menggunakan Plotly, beserta ringkasan statistik.
#
# Cara Menjalankan:
# 1. Simpan kode ini sebagai file Python (misal: app.py).
# 2. Pastikan library terinstal: pip install streamlit pandas plotly
# 3. Jalankan dari terminal: streamlit run app.py
# ==============================================================================

import streamlit as st
import random
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio
from plotly.subplots import make_subplots
import io
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import base64

# ==============================================================================
# BAGIAN 1: KELAS DAN LOGIKA INTI PENGEPAKAN
# ==============================================================================

class Item:
    """Mewakili satu barang yang akan dimasukkan ke dalam kontainer."""
    def __init__(self, dx, dy, dz, weight, name=None, stackable=True, fragile=False, max_stack_weight=None):
        self.dx = float(dx)
        self.dy = float(dy)
        self.dz = float(dz)
        self.weight = float(weight)
        self.volume = self.dx * self.dy * self.dz
        self.name = name or f"Item_{self.dx}x{self.dy}x{self.dz}_{self.weight}kg"
        self.stackable = stackable  # Apakah barang ini bisa ditumpuk
        self.fragile = fragile      # Apakah barang ini mudah pecah/rusak
        self.max_stack_weight = max_stack_weight or (weight * 10 if stackable else 0)  # Berat maksimal yang bisa ditahan
        
        # Menghasilkan semua 6 kemungkinan orientasi rotasi
        self.orientations = list(set([
            (self.dx, self.dy, self.dz),
            (self.dx, self.dz, self.dy),
            (self.dy, self.dx, self.dz),
            (self.dy, self.dz, self.dx),
            (self.dz, self.dx, self.dy),
            (self.dz, self.dy, self.dx)
        ]))

    def __repr__(self):
        return self.name

class ContainerPackingEnv:
    """Lingkungan yang mengelola proses pengepakan barang ke dalam kontainer."""
    def __init__(self, container_size=(10, 10, 10), items=[], max_containers=50, max_weight_per_container=3000):
        self.container_size = container_size
        self.width, self.depth, self.height = container_size
        # Heuristik: Urutkan barang dari yang terbesar ke terkecil untuk efisiensi
        self.items = sorted(items, key=lambda x: (-x.volume, -x.weight))
        self.max_containers = max_containers
        self.max_weight_per_container = max_weight_per_container
        self.reset()

    def reset(self):
        """Mereset lingkungan ke keadaan awal."""
        self.containers = []
        self.unplaced = self.items.copy()
        self.placed_items = []
        self._add_new_container()

    def _add_new_container(self):
        """Menambahkan kontainer baru jika batas belum tercapai."""
        if len(self.containers) < self.max_containers:
            self.containers.append({
                'free': [(0, 0, 0, self.width, self.depth, self.height)], # (x, y, z, w, d, h)
                'placed': [],
                'weight': 0,
                'volume_used': 0
            })
            return True
        return False

    def _can_place(self, container, item, space):
        """Memeriksa apakah sebuah item dapat ditempatkan di ruang kosong tertentu."""
        sx, sy, sz, sw, sd, sh = space
        # Cek dimensi
        if item.dx > sw or item.dy > sd or item.dz > sh:
            return False
            
        # Cek tabrakan dengan item lain
        for placed in container['placed']:
            pi = placed['item']
            px, py, pz = placed['x'], placed['y'], placed['z']
            if not (sx + item.dx <= px or sx >= px + pi.dx or
                    sy + item.dy <= py or sy >= py + pi.dy or
                    sz + item.dz <= pz or sz >= pz + pi.dz):
                return False
        
        # Cek kondisi fragile dan stackable
        if not self._check_stacking_rules(container, item, (sx, sy, sz)):
            return False
            
        return True
    
    def _check_stacking_rules(self, container, item, pos):
        """Memeriksa aturan stacking untuk barang fragile dan stackable."""
        x, y, z = pos
        
        # Jika item fragile, tidak boleh ada yang di atasnya
        if item.fragile:
            for placed in container['placed']:
                pi = placed['item']
                px, py, pz = placed['x'], placed['y'], placed['z']
                # Cek apakah ada item lain yang akan berada di atas item fragile ini
                if (px < x + item.dx and px + pi.dx > x and 
                    py < y + item.dy and py + pi.dy > y and 
                    pz >= z + item.dz):
                    return False
        
        # Cek beban di bawah item ini
        items_below = []
        for placed in container['placed']:
            pi = placed['item']
            px, py, pz = placed['x'], placed['y'], placed['z']
            # Item di bawah jika memiliki overlap horizontal dan berada di bawah
            if (px < x + item.dx and px + pi.dx > x and 
                py < y + item.dy and py + pi.dy > y and 
                pz + pi.dz <= z):
                items_below.append(placed)
        
        # Cek kapasitas beban untuk item di bawah
        for placed_below in items_below:
            pi = placed_below['item']
            if not pi.stackable:
                return False  # Item di bawah tidak bisa ditumpuk
            
            # Hitung total berat yang akan ditahan item di bawah
            current_weight_above = self._calculate_weight_above(container, placed_below)
            if current_weight_above + item.weight > pi.max_stack_weight:
                return False  # Melebihi kapasitas beban
        
        return True
    
    def _calculate_weight_above(self, container, base_item):
        """Menghitung total berat yang ditahan oleh suatu item."""
        total_weight = 0
        bx, by, bz = base_item['x'], base_item['y'], base_item['z']
        base = base_item['item']
        
        for placed in container['placed']:
            pi = placed['item']
            px, py, pz = placed['x'], placed['y'], placed['z']
            
            # Item di atas jika memiliki overlap horizontal dan berada di atas
            if (px < bx + base.dx and px + pi.dx > bx and 
                py < by + base.dy and py + pi.dy > by and 
                pz >= bz + base.dz):
                total_weight += pi.weight
        
        return total_weight

    def _update_free_spaces(self, container, space, pos, item):
        """Memperbarui daftar ruang kosong setelah item ditempatkan."""
        container['free'].remove(space)
        sx, sy, sz, sw, sd, sh = space
        x, y, z = pos

        # Tambahkan 3 ruang baru yang mungkin terbentuk di sekitar item yang baru ditempatkan
        # Ruang di kanan (sepanjang sumbu X/lebar)
        if item.dx < sw:
            container['free'].append((x + item.dx, y, z, sw - item.dx, sd, sh))
        # Ruang di depan (sepanjang sumbu Y/kedalaman)
        if item.dy < sd:
            container['free'].append((x, y + item.dy, z, sw, sd - item.dy, sh))
        # Ruang di atas (sepanjang sumbu Z/tinggi)
        if item.dz < sh:
            container['free'].append((x, y, z + item.dz, sw, sd, sh - item.dz))

        # Hapus ruang yang sepenuhnya terkandung di dalam ruang lain untuk mengurangi redundansi
        container['free'] = sorted(list(set(f for f in container['free'] if f[3]>0 and f[4]>0 and f[5]>0)))

    def step(self):
        """Melakukan satu langkah dalam proses pengepakan (menempatkan satu item)."""
        if not self.unplaced:
            return True, {} # Selesai, semua item ditempatkan

        item_to_place = self.unplaced[0]
        best_fit = None
        best_score = float('inf')

        for container in self.containers:
            if container['weight'] + item_to_place.weight > self.max_weight_per_container:
                continue

            for orientation in item_to_place.orientations:
                temp_item = Item(*orientation, item_to_place.weight, item_to_place.name, 
                               item_to_place.stackable, item_to_place.fragile, item_to_place.max_stack_weight)
                
                # Heuristik: prioritaskan ruang yang paling bawah, paling kiri, paling depan
                # Untuk item fragile, prioritaskan tempat yang lebih tinggi
                if item_to_place.fragile:
                    sorted_spaces = sorted(container['free'], key=lambda s: (-s[2], s[1], s[0]))
                else:
                    sorted_spaces = sorted(container['free'], key=lambda s: (s[2], s[1], s[0]))
                    
                for space in sorted_spaces:
                    if self._can_place(container, temp_item, space):
                        # Skor berdasarkan sisa ruang (Best-Fit) dan ketinggian
                        # Untuk item fragile, berikan bonus untuk posisi tinggi
                        height_bonus = space[2] * 0.5 if item_to_place.fragile else space[2] * 1.5
                        score = (space[3] - temp_item.dx) + (space[4] - temp_item.dy) + height_bonus
                        if score < best_score:
                            best_score = score
                            best_fit = (container, temp_item, space)

        if best_fit:
            container, item, space = best_fit
            pos = (space[0], space[1], space[2])
            
            self.unplaced.pop(0)
            container['placed'].append({'item': item, 'x': pos[0], 'y': pos[1], 'z': pos[2]})
            container['weight'] += item.weight
            container['volume_used'] += item.volume
            self.placed_items.append(item)
            
            self._update_free_spaces(container, space, pos, item)
            return False, {'placed': True}

        # Jika tidak muat di kontainer mana pun, coba buat yang baru
        if self._add_new_container():
            return self.step() # Coba lagi dengan kontainer baru
        
        # Jika tidak bisa menambah kontainer dan item tidak muat
        return True, {'error': 'Tidak dapat menempatkan item dan kontainer baru tidak diizinkan.'}

def run_packing_simulation(env):
    """Menjalankan seluruh simulasi pengepakan sampai selesai."""
    done = False
    while not done and env.unplaced:
        done, info = env.step()
        if info.get('error'):
            break
    return env

# ==============================================================================
# BAGIAN 2: FUNGSI VISUALISASI DENGAN PLOTLY
# ==============================================================================

def create_plotly_visualization(env):
    """Membuat visualisasi 3D menggunakan Plotly."""
    fig = make_subplots(
        rows=1, cols=1, 
        specs=[[{'type': 'scatter3d'}]],
        subplot_titles=["Visualisasi 3D Pengepakan Kontainer"]
    )

    # Generate colors for different item types
    unique_names = list(set(item.name for item in env.placed_items))
    colors = px.colors.qualitative.Set3[:len(unique_names)]
    if len(unique_names) > len(colors):
        colors = colors * (len(unique_names) // len(colors) + 1)
    
    color_map = {name: colors[i] for i, name in enumerate(unique_names)}

    offset_x = 0
    
    for container_idx, container in enumerate(env.containers):
        # Draw container outline
        W, L, H = env.width, env.depth, env.height
        
        # Container edges
        container_edges = [
            # Bottom edges
            [offset_x, offset_x + W, offset_x + W, offset_x, offset_x],
            [0, 0, L, L, 0],
            [0, 0, 0, 0, 0],
            
            # Top edges  
            [offset_x, offset_x + W, offset_x + W, offset_x, offset_x],
            [0, 0, L, L, 0],
            [H, H, H, H, H],
            
            # Vertical edges
            [offset_x, offset_x], [0, 0], [0, H],
            [offset_x + W, offset_x + W], [0, 0], [0, H],
            [offset_x + W, offset_x + W], [L, L], [0, H],
            [offset_x, offset_x], [L, L], [0, H]
        ]
        
        fig.add_trace(go.Scatter3d(
            x=[offset_x, offset_x + W, offset_x + W, offset_x, offset_x, 
               offset_x, offset_x + W, offset_x + W, offset_x, offset_x,
               offset_x, offset_x, None, offset_x + W, offset_x + W, None,
               offset_x + W, offset_x + W, None, offset_x, offset_x],
            y=[0, 0, L, L, 0, 
               0, 0, L, L, 0,
               0, 0, None, 0, 0, None,
               L, L, None, L, L],
            z=[0, 0, 0, 0, 0,
               H, H, H, H, H,
               0, H, None, 0, H, None,
               0, H, None, 0, H],
            mode='lines',
            line=dict(color='black', width=2),
            name=f'Kontainer {container_idx + 1}',
            showlegend=(container_idx == 0)
        ))

        # Draw placed items as proper 3D boxes
        for placement in container['placed']:
            item = placement['item']
            x, y, z = placement['x'], placement['y'], placement['z']
            
            # Create all 8 vertices of the box
            vertices_x = [
                x + offset_x, x + item.dx + offset_x, x + item.dx + offset_x, x + offset_x,  # bottom face
                x + offset_x, x + item.dx + offset_x, x + item.dx + offset_x, x + offset_x   # top face
            ]
            vertices_y = [
                y, y, y + item.dy, y + item.dy,  # bottom face
                y, y, y + item.dy, y + item.dy   # top face
            ]
            vertices_z = [
                z, z, z, z,                      # bottom face
                z + item.dz, z + item.dz, z + item.dz, z + item.dz  # top face
            ]
            
            # Define the 12 triangular faces of the box (2 triangles per face)
            i = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 0, 0, 1, 1, 2, 2, 3, 3]
            j = [1, 3, 2, 0, 3, 1, 0, 2, 5, 7, 6, 4, 7, 5, 4, 6, 4, 1, 5, 2, 6, 3, 7, 0]
            k = [3, 1, 0, 2, 1, 3, 2, 0, 7, 5, 4, 6, 5, 7, 6, 4, 1, 4, 2, 5, 3, 6, 0, 7]
            
            fig.add_trace(go.Mesh3d(
                x=vertices_x,
                y=vertices_y, 
                z=vertices_z,
                i=i, j=j, k=k,
                color=color_map.get(item.name, 'blue'),
                opacity=0.7 if not item.fragile else 0.9,  # Item fragile lebih opaque
                name=item.name,
                showlegend=False,
                hovertemplate=f"<b>{item.name}</b><br>" +
                             f"Dimensi: {item.dx:.1f} x {item.dy:.1f} x {item.dz:.1f} cm<br>" +
                             f"Berat: {item.weight:.1f} kg<br>" +
                             f"Volume: {item.volume:.1f} cm³<br>" +
                             f"Posisi: ({x:.1f}, {y:.1f}, {z:.1f})<br>" +
                             f"Stackable: {'Ya' if item.stackable else 'Tidak'}<br>" +
                             f"Fragile: {'Ya' if item.fragile else 'Tidak'}<br>" +
                             f"Max Stack Weight: {item.max_stack_weight:.1f} kg<extra></extra>"
            ))            # Add box wireframe for better visibility
            box_x = [
                x + offset_x, x + item.dx + offset_x, x + item.dx + offset_x, x + offset_x, x + offset_x, None,
                x + offset_x, x + item.dx + offset_x, x + item.dx + offset_x, x + offset_x, x + offset_x, None,
                x + offset_x, x + offset_x, None, x + item.dx + offset_x, x + item.dx + offset_x, None,
                x + item.dx + offset_x, x + item.dx + offset_x, None, x + offset_x, x + offset_x
            ]
            box_y = [
                y, y, y + item.dy, y + item.dy, y, None,
                y, y, y + item.dy, y + item.dy, y, None,
                y, y, None, y, y, None,
                y + item.dy, y + item.dy, None, y + item.dy, y + item.dy
            ]
            box_z = [
                z, z, z, z, z, None,
                z + item.dz, z + item.dz, z + item.dz, z + item.dz, z + item.dz, None,
                z, z + item.dz, None, z, z + item.dz, None,
                z, z + item.dz, None, z, z + item.dz
            ]
            
            fig.add_trace(go.Scatter3d(
                x=box_x, y=box_y, z=box_z,
                mode='lines',
                line=dict(color='black', width=1),
                showlegend=False,
                hoverinfo='skip'
            ))
        
        offset_x += env.width * 1.2  # Space between containers

    # Update layout for better visualization
    fig.update_layout(
        scene=dict(
            xaxis_title="Lebar (cm)",
            yaxis_title="Panjang (cm)", 
            zaxis_title="Tinggi (cm)",
            aspectmode='data',
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.5)
            )
        ),
        title="Visualisasi 3D Hasil Pengepakan Kontainer",
        height=700,
        showlegend=True
    )

    return fig

def create_multiview_pdf(env, base_fig):
    """
    Membuat PDF dengan multiple views dari objek figur Plotly yang sudah ada.
    """
    fig = go.Figure(base_fig)

    # 6 POV kamera
    camera_views = {
        "Tampak Isometrik": dict(eye=dict(x=1.5, y=1.5, z=1.5), up=dict(x=0, y=0, z=1)),
        "Tampak Atas":      dict(eye=dict(x=0, y=0, z=2.5), up=dict(x=0, y=1, z=0)),
        "Tampak Depan":     dict(eye=dict(x=0, y=-2.5, z=0), up=dict(x=0, y=0, z=1)),
        "Tampak Belakang":  dict(eye=dict(x=0, y=2.5, z=0), up=dict(x=0, y=0, z=1)),
        "Tampak Kanan":     dict(eye=dict(x=2.5, y=0, z=0), up=dict(x=0, y=0, z=1)),
        "Tampak Kiri":      dict(eye=dict(x=-2.5, y=0, z=0), up=dict(x=0, y=0, z=1)),
    }
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []
    
    story.append(Paragraph("📦 Laporan Multi-View Pengepakan Kontainer", styles['h1']))
    story.append(Spacer(1, 20))
    
    # Tabel ringkasan
    summary_data = [['Metrik', 'Nilai']]
    summary_data.append(['Kontainer Digunakan', str(len(env.containers))])
    summary_data.append(['Barang Ditempatkan', str(len(env.placed_items))])
    summary_data.append(['Barang Tidak Muat', str(len(env.unplaced))])
    total_vol = len(env.containers) * env.width * env.depth * env.height
    used_vol = sum(c['volume_used'] for c in env.containers)
    eff = (used_vol / total_vol * 100) if total_vol > 0 else 0
    summary_data.append(['Efisiensi Volume', f'{eff:.1f}%'])
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue), ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12), ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 30))

    # Loop melalui setiap sudut pandang, update kamera, dan render gambar
    images_in_row = []
    for view_name, camera_setting in camera_views.items():
        fig.update_layout(scene_camera=camera_setting, title=view_name)
        
        # Konversi figur menjadi gambar PNG
        img_bytes = pio.to_image(fig, format="png", width=600, height=450, scale=2)
        img = Image(io.BytesIO(img_bytes), width=4.5*inch, height=3.375*inch)
        images_in_row.append(img)
        
        if len(images_in_row) == 2:
            table = Table([images_in_row], colWidths=[5*inch, 5*inch])
            story.append(table)
            story.append(Spacer(1, 15))
            images_in_row = []
    
    if images_in_row:
        table = Table([images_in_row])
        story.append(table)

    doc.build(story)
    buffer.seek(0)
    return buffer

# ==============================================================================
# BAGIAN 3: ANTARMUKA PENGGUNA STREAMLIT
# ==============================================================================

st.set_page_config(layout="wide", page_title="3D Container Packing")
st.title("📦 Aplikasi Visualisasi Pengepakan Kontainer 3D Interaktif")
st.write("Atur parameter di sidebar, tambahkan barang, lalu jalankan proses untuk melihat visualisasi pengepakan 3D yang bisa digeser dan diputar.")

# --- SIDEBAR UNTUK KONFIGURASI ---
with st.sidebar:
    st.header("⚙️ Konfigurasi")

    # Inisialisasi session state untuk menyimpan daftar item
    if 'items_to_pack' not in st.session_state:
        st.session_state.items_to_pack = []

    # Pilihan Ukuran Kontainer
    CONTAINER_SIZES = {
        "20ft Standard": (235.2, 589.8, 239.5), # Lebar, Panjang, Tinggi (cm)
        "40ft Standard": (235.2, 1203.2, 239.5),
        "40ft High Cube": (235.2, 1203.2, 269.8),
        "Custom": (300, 400, 250)  # Added custom option for testing
    }
    container_choice = st.selectbox("Pilih Ukuran Kontainer:", list(CONTAINER_SIZES.keys()))
    
    if container_choice == "Custom":
        col1, col2 = st.columns(2)
        W = col1.number_input("Lebar Kontainer (cm)", min_value=50.0, value=300.0, step=10.0)
        L = col2.number_input("Panjang Kontainer (cm)", min_value=50.0, value=400.0, step=10.0)
        H = st.number_input("Tinggi Kontainer (cm)", min_value=50.0, value=250.0, step=10.0)
    else:
        W, L, H = CONTAINER_SIZES[container_choice]
        st.info(f"Dimensi: {W} x {L} x {H} cm")

    max_weight = st.number_input(
        "Berat Maksimum Kontainer (kg)", 
        min_value=1000, value=24000, step=1000,
        help="Berat kargo maksimum yang diizinkan."
    )

    st.markdown("---")
    st.subheader("Tambahkan Barang")

    # Form untuk menambah item
    with st.form("add_item_form", clear_on_submit=True):
        item_name = st.text_input("Nama Barang", "Kardus")
        col1, col2 = st.columns(2)
        item_dx = col1.number_input("Lebar (cm)", min_value=1.0, value=50.0, format="%.1f")
        item_dy = col2.number_input("Panjang (cm)", min_value=1.0, value=40.0, format="%.1f")
        item_dz = col1.number_input("Tinggi (cm)", min_value=1.0, value=30.0, format="%.1f")
        item_weight = col2.number_input("Berat (kg)", min_value=0.1, value=10.0, format="%.1f")
        item_quantity = st.number_input("Jumlah", min_value=1, value=10, step=1)
        
        # Opsi tambahan untuk stacking dan fragile
        st.markdown("**Karakteristik Barang:**")
        col3, col4 = st.columns(2)
        item_stackable = col3.checkbox("Bisa Ditumpuk", value=True, help="Apakah barang ini bisa dijadikan dasar tumpukan?")
        item_fragile = col4.checkbox("Mudah Pecah/Rusak", value=False, help="Apakah barang ini tidak boleh ditindih?")
        
        # Berat maksimal yang bisa ditahan (hanya aktif jika stackable)
        if item_stackable:
            item_max_stack = st.number_input(
                "Beban Maksimal yang Bisa Ditahan (kg)", 
                min_value=0.0, value=item_weight * 10, format="%.1f",
                help="Berat maksimal yang bisa ditumpuk di atas barang ini"
            )
        else:
            item_max_stack = 0.0
        
        if st.form_submit_button("➕ Tambah Barang"):
            st.session_state.items_to_pack.append({
                "name": item_name, "dx": item_dx, "dy": item_dy, "dz": item_dz,
                "weight": item_weight, "quantity": item_quantity,
                "stackable": item_stackable, "fragile": item_fragile, "max_stack_weight": item_max_stack
            })
            fragile_text = " (Fragile)" if item_fragile else ""
            stackable_text = " (Non-stackable)" if not item_stackable else ""
            st.success(f"{item_quantity}x {item_name}{fragile_text}{stackable_text} ditambahkan!")

    # Quick add sample items
    st.markdown("**Contoh Cepat:**")
    col1, col2 = st.columns(2)
    if col1.button("📦 Sample Boxes", help="Tambah beberapa kardus ukuran berbeda"):
        sample_items = [
            {"name": "Kardus Kecil", "dx": 30, "dy": 40, "dz": 20, "weight": 5, "quantity": 15, "stackable": True, "fragile": False, "max_stack_weight": 50},
            {"name": "Kardus Sedang", "dx": 50, "dy": 60, "dz": 40, "weight": 12, "quantity": 8, "stackable": True, "fragile": False, "max_stack_weight": 120},
            {"name": "Kardus Besar", "dx": 80, "dy": 100, "dz": 60, "weight": 25, "quantity": 3, "stackable": True, "fragile": False, "max_stack_weight": 100}
        ]
        st.session_state.items_to_pack.extend(sample_items)
        st.success("Sample boxes ditambahkan!")
        st.rerun()
    
    if col2.button("🎁 Sample Products", help="Tambah berbagai produk dengan karakteristik khusus"):
        sample_items = [
            {"name": "TV 32inch", "dx": 75, "dy": 15, "dz": 45, "weight": 8, "quantity": 2, "stackable": False, "fragile": True, "max_stack_weight": 0},
            {"name": "Laptop Box", "dx": 40, "dy": 30, "dz": 8, "weight": 3, "quantity": 5, "stackable": True, "fragile": True, "max_stack_weight": 10},
            {"name": "Furniture Box", "dx": 120, "dy": 80, "dz": 40, "weight": 30, "quantity": 2, "stackable": False, "fragile": False, "max_stack_weight": 0},
            {"name": "Glass Items", "dx": 60, "dy": 40, "dz": 25, "weight": 15, "quantity": 4, "stackable": False, "fragile": True, "max_stack_weight": 0},
            {"name": "Heavy Equipment", "dx": 100, "dy": 80, "dz": 50, "weight": 50, "quantity": 2, "stackable": True, "fragile": False, "max_stack_weight": 200}
        ]
        st.session_state.items_to_pack.extend(sample_items)
        st.success("Sample products dengan karakteristik khusus ditambahkan!")
        st.rerun()

    # Tampilkan dan kelola daftar item
    st.markdown("---")
    st.subheader("Daftar Barang")
    if not st.session_state.items_to_pack:
        st.info("Belum ada barang yang ditambahkan.")
    else:
        total_items = sum(item['quantity'] for item in st.session_state.items_to_pack)
        total_weight = sum(item['quantity'] * item['weight'] for item in st.session_state.items_to_pack)
        st.info(f"Total: {total_items} item, {total_weight:.1f} kg")
        
        for i, item in enumerate(st.session_state.items_to_pack):
            col1, col2 = st.columns([4, 1])
            
            # Buat label dengan karakteristik barang
            characteristics = []
            if item.get('fragile', False):
                characteristics.append("🔺 Fragile")
            if not item.get('stackable', True):
                characteristics.append("⚠️ Non-stackable")
            if item.get('stackable', True) and item.get('max_stack_weight', 0) > 0:
                characteristics.append(f"📚 Max: {item.get('max_stack_weight', 0)}kg")
            
            char_text = f" [{', '.join(characteristics)}]" if characteristics else ""
            
            col1.write(f"• {item['quantity']}x **{item['name']}** ({item['dx']}×{item['dy']}×{item['dz']} cm, {item['weight']} kg){char_text}")
            if col2.button("❌", key=f"del_{i}", help="Hapus item ini"):
                st.session_state.items_to_pack.pop(i)
                st.rerun()
        
        if st.button("🗑️ Hapus Semua Barang"):
            st.session_state.items_to_pack = []
            st.rerun()

# --- AREA UTAMA UNTUK HASIL ---
st.markdown("---")

if st.button("🚀 Mulai Proses Pengepakan", type="primary", use_container_width=True):
    if not st.session_state.items_to_pack:
        st.warning("Mohon tambahkan setidaknya satu jenis barang di sidebar.")
    else:
        with st.spinner("Menghitung tata letak optimal... Ini mungkin butuh beberapa saat."):
            all_items = [
                Item(dx=ic['dx'], dy=ic['dy'], dz=ic['dz'], weight=ic['weight'], 
                     name=ic['name'], stackable=ic.get('stackable', True), 
                     fragile=ic.get('fragile', False), max_stack_weight=ic.get('max_stack_weight', 0))
                for ic in st.session_state.items_to_pack for _ in range(ic['quantity'])
            ]
            env = ContainerPackingEnv(container_size=(W, L, H), items=all_items, max_weight_per_container=max_weight)
            env = run_packing_simulation(env)

        st.success("🎉 Proses Pengepakan Selesai!")
        st.subheader("📊 Ringkasan Hasil")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Kontainer Digunakan", f"{len(env.containers)}")
        col2.metric("Barang Ditempatkan", f"{len(env.placed_items)}")
        col3.metric("Barang Tidak Muat", f"{len(env.unplaced)}")
        
        total_container_volume = len(env.containers) * W * L * H
        used_volume = sum(c['volume_used'] for c in env.containers)
        efficiency = (used_volume / total_container_volume * 100) if total_container_volume > 0 else 0
        col4.metric("Efisiensi Volume", f"{efficiency:.1f}%")
        
        st.subheader("🌐 Visualisasi 3D Interaktif")
        if env.placed_items:
            base_fig = create_plotly_visualization(env)
            st.plotly_chart(base_fig, use_container_width=True)
            
            st.subheader("📤 Ekspor Hasil")
            
            with st.spinner("🔄 Menyiapkan data PDF..."):
                pdf_buffer = create_multiview_pdf(env, base_fig)
                st.download_button(
                    label="📄 Unduh Laporan PDF Multi-View",
                    data=pdf_buffer,
                    file_name="Laporan Packing Multi-View.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

        else:
            st.info("Tidak ada barang yang berhasil ditempatkan untuk divisualisasikan.")

        if env.unplaced:
            with st.expander("⚠️ Detail barang yang tidak bisa dimasukkan", expanded=True):
                st.warning("**Barang tidak muat karena kontainer penuh atau aturan penempatan:**")
                unplaced_summary = {}
                for item in env.unplaced:
                    key = item.name
                    unplaced_summary[key] = unplaced_summary.get(key, 0) + 1
                for name, count in unplaced_summary.items():
                    st.write(f"📦 {count}x {name}")
else:
    st.info("👆 Atur konfigurasi di sidebar dan klik 'Mulai Proses Pengepakan' untuk melihat hasilnya.")
    
    # Show some helpful information
    with st.expander("ℹ️ Informasi Aplikasi"):
        st.markdown("""
        ### Fitur Aplikasi:
        - **Algoritma Pengepakan**: Menggunakan algoritma Bottom-Left-Fill dengan optimasi orientasi
        - **Visualisasi 3D**: Interaktif dengan Plotly (dapat digeser, diperbesar, diputar)
        - **Multi-Kontainer**: Otomatis menggunakan kontainer tambahan jika diperlukan
        - **Optimasi Berat**: Mempertimbangkan batas berat maksimum kontainer
        - **🆕 Stacking Rules**: Mendukung aturan penumpukan dengan batas beban maksimal
        - **🆕 Fragile Items**: Barang fragile tidak boleh ditindih dan ditempatkan di posisi aman
        - **🆕 Non-Stackable Items**: Barang yang tidak bisa dijadikan dasar tumpukan
        - **📄 Export PDF Multi-View**: Generate laporan PDF dengan 4 sudut pandang berbeda
        
        ### Cara Penggunaan:
        1. Pilih ukuran kontainer atau gunakan custom
        2. Tambahkan barang dengan dimensi, berat, dan karakteristik (stackable/fragile)
        3. Tentukan batas beban maksimal untuk barang yang bisa ditumpuk
        4. Gunakan tombol "Sample" untuk mencoba contoh dengan berbagai karakteristik
        5. Klik "Mulai Proses Pengepakan" untuk melihat hasil
        6. Lihat visualisasi 3D dengan informasi detail karakteristik setiap barang
        7. Export hasil ke CSV atau PDF multi-view report
        
        ### Karakteristik Barang:
        - **🔺 Fragile**: Barang mudah pecah/rusak, tidak boleh ditindih
        - **⚠️ Non-stackable**: Barang tidak bisa dijadikan dasar tumpukan
        - **📚 Max Stack Weight**: Berat maksimal yang bisa ditahan oleh barang stackable
        """)
