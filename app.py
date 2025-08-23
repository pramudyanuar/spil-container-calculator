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
    def __init__(self, dx, dy, dz, weight, name=None):
        self.dx = float(dx)
        self.dy = float(dy)
        self.dz = float(dz)
        self.weight = float(weight)
        self.volume = self.dx * self.dy * self.dz
        self.name = name or f"Item_{self.dx}x{self.dy}x{self.dz}_{self.weight}kg"
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
        # Cek tabrakan dengan item lain (seharusnya tidak terjadi dengan logika ruang bebas, tapi sebagai pengaman)
        for placed in container['placed']:
            pi = placed['item']
            px, py, pz = placed['x'], placed['y'], placed['z']
            if not (sx + item.dx <= px or sx >= px + pi.dx or
                    sy + item.dy <= py or sy >= py + pi.dy or
                    sz + item.dz <= pz or sz >= pz + pi.dz):
                return False
        return True

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
                temp_item = Item(*orientation, item_to_place.weight, item_to_place.name)
                
                # Heuristik: prioritaskan ruang yang paling bawah, paling kiri, paling depan
                for space in sorted(container['free'], key=lambda s: (s[2], s[1], s[0])):
                    if self._can_place(container, temp_item, space):
                        # Skor berdasarkan sisa ruang (Best-Fit) dan ketinggian
                        score = (space[3] - temp_item.dx) + (space[4] - temp_item.dy) + space[2] * 1.5
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
                opacity=0.7,
                name=item.name,
                showlegend=False,
                hovertemplate=f"<b>{item.name}</b><br>" +
                             f"Dimensi: {item.dx:.1f} x {item.dy:.1f} x {item.dz:.1f} cm<br>" +
                             f"Berat: {item.weight:.1f} kg<br>" +
                             f"Volume: {item.volume:.1f} cm³<br>" +
                             f"Posisi: ({x:.1f}, {y:.1f}, {z:.1f})<extra></extra>"
            ))
            
            # Add box wireframe for better visibility
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

def create_multiview_pdf(env):
    """Membuat PDF dengan multiple views dari visualisasi 3D."""
    
    # Create different camera angles for multiple views
    camera_views = {
        "Front View": dict(eye=dict(x=0, y=-2, z=0.5)),
        "Side View": dict(eye=dict(x=2, y=0, z=0.5)),
        "Top View": dict(eye=dict(x=0, y=0, z=2)),
        "Isometric": dict(eye=dict(x=1.5, y=1.5, z=1.5))
    }
    
    # Generate colors for different item types
    unique_names = list(set(item.name for item in env.placed_items))
    colors = px.colors.qualitative.Set3[:len(unique_names)]
    if len(unique_names) > len(colors):
        colors = colors * (len(unique_names) // len(colors) + 1)
    color_map = {name: colors[i] for i, name in enumerate(unique_names)}
    
    # Create PDF buffer
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), 
                          rightMargin=30, leftMargin=30, topMargin=50, bottomMargin=30)
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=1  # Center
    )
    
    story = []
    
    # Title
    story.append(Paragraph("📦 Container Packing 3D Multi-View Report", title_style))
    story.append(Spacer(1, 20))
    
    # Summary statistics
    summary_data = [
        ['Metric', 'Value'],
        ['Containers Used', str(len(env.containers))],
        ['Items Placed', str(len(env.placed_items))],
        ['Items Unplaced', str(len(env.unplaced))],
    ]
    
    # Calculate efficiency
    total_container_volume = len(env.containers) * env.width * env.depth * env.height
    used_volume = sum(c['volume_used'] for c in env.containers)
    efficiency = (used_volume / total_container_volume * 100) if total_container_volume > 0 else 0
    summary_data.append(['Volume Efficiency', f'{efficiency:.1f}%'])
    
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 30))
    
    # Create and save multiple view images
    image_objects = []
    
    for view_name, camera in camera_views.items():
        # Create figure for this view
        fig = go.Figure()
        
        offset_x = 0
        
        for container_idx, container in enumerate(env.containers):
            # Draw container outline
            W, L, H = env.width, env.depth, env.height
            
            # Container wireframe
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
                name=f'Container {container_idx + 1}',
                showlegend=False
            ))

            # Draw placed items
            for placement in container['placed']:
                item = placement['item']
                x, y, z = placement['x'], placement['y'], placement['z']
                
                # Create all 8 vertices of the box
                vertices_x = [
                    x + offset_x, x + item.dx + offset_x, x + item.dx + offset_x, x + offset_x,
                    x + offset_x, x + item.dx + offset_x, x + item.dx + offset_x, x + offset_x
                ]
                vertices_y = [
                    y, y, y + item.dy, y + item.dy,
                    y, y, y + item.dy, y + item.dy
                ]
                vertices_z = [
                    z, z, z, z,
                    z + item.dz, z + item.dz, z + item.dz, z + item.dz
                ]
                
                # Define triangular faces
                i = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 0, 0, 1, 1, 2, 2, 3, 3]
                j = [1, 3, 2, 0, 3, 1, 0, 2, 5, 7, 6, 4, 7, 5, 4, 6, 4, 1, 5, 2, 6, 3, 7, 0]
                k = [3, 1, 0, 2, 1, 3, 2, 0, 7, 5, 4, 6, 5, 7, 6, 4, 1, 4, 2, 5, 3, 6, 0, 7]
                
                fig.add_trace(go.Mesh3d(
                    x=vertices_x, y=vertices_y, z=vertices_z,
                    i=i, j=j, k=k,
                    color=color_map.get(item.name, 'blue'),
                    opacity=0.8,
                    showlegend=False
                ))
            
            offset_x += env.width * 1.2
        
        # Update layout for this view
        fig.update_layout(
            scene=dict(
                xaxis_title="Width (cm)",
                yaxis_title="Length (cm)", 
                zaxis_title="Height (cm)",
                aspectmode='data',
                camera=camera
            ),
            title=f"{view_name}",
            width=800, height=600,
            showlegend=False,
            margin=dict(l=0, r=0, t=40, b=0)
        )
        
        # Convert to image
        img_bytes = fig.to_image(format="png", width=800, height=600)
        img_buffer = io.BytesIO(img_bytes)
        
        # Create reportlab image
        img = Image(img_buffer, width=6*inch, height=4.5*inch)
        story.append(Paragraph(f"<b>{view_name}</b>", styles['Heading2']))
        story.append(Spacer(1, 10))
        story.append(img)
        story.append(Spacer(1, 20))
    
    # Container details table
    story.append(Paragraph("Container Details", styles['Heading2']))
    story.append(Spacer(1, 10))
    
    container_details = [['Container', 'Items', 'Weight (kg)', 'Volume Used (%)']]
    
    for i, c in enumerate(env.containers):
        volume_util = (c['volume_used'] / (env.width * env.depth * env.height) * 100)
        container_details.append([
            f'Container {i+1}',
            str(len(c['placed'])),
            f"{c['weight']:.1f}",
            f"{volume_util:.1f}%"
        ])
    
    detail_table = Table(container_details, colWidths=[1.5*inch, 1*inch, 1.5*inch, 1.5*inch])
    detail_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(detail_table)
    
    # Build PDF
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
        
        if st.form_submit_button("➕ Tambah Barang"):
            st.session_state.items_to_pack.append({
                "name": item_name, "dx": item_dx, "dy": item_dy, "dz": item_dz,
                "weight": item_weight, "quantity": item_quantity
            })
            st.success(f"{item_quantity}x {item_name} ditambahkan!")

    # Quick add sample items
    st.markdown("**Contoh Cepat:**")
    col1, col2 = st.columns(2)
    if col1.button("📦 Sample Boxes", help="Tambah beberapa kardus ukuran berbeda"):
        sample_items = [
            {"name": "Kardus Kecil", "dx": 30, "dy": 40, "dz": 20, "weight": 5, "quantity": 15},
            {"name": "Kardus Sedang", "dx": 50, "dy": 60, "dz": 40, "weight": 12, "quantity": 8},
            {"name": "Kardus Besar", "dx": 80, "dy": 100, "dz": 60, "weight": 25, "quantity": 3}
        ]
        st.session_state.items_to_pack.extend(sample_items)
        st.success("Sample boxes ditambahkan!")
        st.rerun()
    
    if col2.button("🎁 Sample Products", help="Tambah berbagai produk"):
        sample_items = [
            {"name": "TV 32inch", "dx": 75, "dy": 15, "dz": 45, "weight": 8, "quantity": 2},
            {"name": "Laptop Box", "dx": 40, "dy": 30, "dz": 8, "weight": 3, "quantity": 5},
            {"name": "Furniture Box", "dx": 120, "dy": 80, "dz": 40, "weight": 30, "quantity": 2}
        ]
        st.session_state.items_to_pack.extend(sample_items)
        st.success("Sample products ditambahkan!")
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
            col1.write(f"• {item['quantity']}x **{item['name']}** ({item['dx']}×{item['dy']}×{item['dz']} cm, {item['weight']} kg)")
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
            # 1. Siapkan daftar item dari input pengguna
            all_items = [
                Item(dx=ic['dx'], dy=ic['dy'], dz=ic['dz'], weight=ic['weight'], name=ic['name'])
                for ic in st.session_state.items_to_pack for _ in range(ic['quantity'])
            ]

            # 2. Filter item yang terlalu besar untuk kontainer
            valid_items = []
            oversized_items = []
            for item in all_items:
                if any(o[0] <= W and o[1] <= L and o[2] <= H for o in item.orientations):
                    valid_items.append(item)
                else:
                    oversized_items.append(f"{item.name} ({item.dx}×{item.dy}×{item.dz} cm)")

            # 3. Jalankan simulasi pengepakan
            env = ContainerPackingEnv(container_size=(W, L, H), items=valid_items, max_weight_per_container=max_weight)
            env = run_packing_simulation(env)

        # 4. Tampilkan hasil
        st.success("🎉 Proses Pengepakan Selesai!")
        
        # Tampilkan Statistik
        st.subheader("📊 Ringkasan Hasil")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Kontainer Digunakan", f"{len(env.containers)}")
        col2.metric("Barang Ditempatkan", f"{len(env.placed_items)}")
        col3.metric("Barang Tidak Muat", f"{len(env.unplaced)}")
        
        # Calculate overall efficiency
        total_container_volume = len(env.containers) * W * L * H
        used_volume = sum(c['volume_used'] for c in env.containers)
        efficiency = (used_volume / total_container_volume * 100) if total_container_volume > 0 else 0
        col4.metric("Efisiensi Volume", f"{efficiency:.1f}%")
        
        # Detail Utilisasi per Kontainer
        st.subheader("📋 Detail per Kontainer")
        container_data = []
        for i, c in enumerate(env.containers):
            volume_util = (c['volume_used'] / (W * L * H) * 100)
            weight_util = (c['weight'] / max_weight * 100)
            container_data.append({
                "Kontainer": f"#{i+1}",
                "Jumlah Item": len(c['placed']),
                "Volume Utilitas": f"{volume_util:.1f}%",
                "Berat": f"{c['weight']:.1f} kg ({weight_util:.1f}%)",
                "Volume Terpakai": f"{c['volume_used']:,.0f} cm³"
            })
        
        df = pd.DataFrame(container_data)
        st.dataframe(df, use_container_width=True)
        
        # Visualisasi 3D Interaktif
        st.subheader("🌐 Visualisasi 3D Interaktif")
        if env.placed_items:
            fig = create_plotly_visualization(env)
            st.plotly_chart(fig, use_container_width=True)
            
            # Item legend
            with st.expander("🏷️ Legend - Jenis Barang"):
                unique_items = {}
                for item in env.placed_items:
                    key = (item.name, item.dx, item.dy, item.dz)
                    if key not in unique_items:
                        unique_items[key] = 0
                    unique_items[key] += 1
                
                for (name, dx, dy, dz), count in unique_items.items():
                    st.write(f"📦 **{name}**: {count} item(s) - {dx}×{dy}×{dz} cm")
        else:
            st.info("Tidak ada barang yang berhasil ditempatkan untuk divisualisasikan.")

        # Daftar Barang yang Tidak Muat
        if env.unplaced or oversized_items:
            with st.expander("⚠️ Detail barang yang tidak bisa dimasukkan", expanded=True):
                if oversized_items:
                    st.error("**Barang terlalu besar untuk kontainer:**")
                    for info in set(oversized_items): 
                        st.write(f"❌ {info}")
                
                if env.unplaced:
                    st.warning("**Barang tidak muat karena kontainer penuh:**")
                    unplaced_summary = {}
                    for item in env.unplaced:
                        key = (item.name, item.dx, item.dy, item.dz)
                        unplaced_summary[key] = unplaced_summary.get(key, 0) + 1
                    for (name, dx, dy, dz), count in unplaced_summary.items():
                        st.write(f"📦 {count}x {name} ({dx}×{dy}×{dz} cm)")

        # Export results option
        # col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 Export Hasil ke CSV"):
                # Create detailed results
                results_data = []
                for container_idx, container in enumerate(env.containers):
                    for placement in container['placed']:
                        item = placement['item']
                        results_data.append({
                            'Kontainer': f'Container_{container_idx + 1}',
                            'Nama_Barang': item.name,
                            'Panjang_cm': item.dx,
                            'Lebar_cm': item.dy, 
                            'Tinggi_cm': item.dz,
                            'Berat_kg': item.weight,
                            'Volume_cm3': item.volume,
                            'Posisi_X': placement['x'],
                            'Posisi_Y': placement['y'],
                            'Posisi_Z': placement['z']
                        })
                
                if results_data:
                    df_export = pd.DataFrame(results_data)
                    csv = df_export.to_csv(index=False)
                    st.download_button(
                        label="💾 Download CSV",
                        data=csv,
                        file_name="container_packing_results.csv",
                        mime="text/csv"
                    )
        
        with col2:
            if st.button("📄 Export 3D Multi-View PDF"):
                with st.spinner("Membuat PDF multi-view... Mohon tunggu..."):
                    try:
                        pdf_buffer = create_multiview_pdf(env)
                        pdf_bytes = pdf_buffer.getvalue()
                        st.write(f"Ukuran PDF: {len(pdf_bytes)} bytes")
                        if not pdf_bytes or len(pdf_bytes) < 1000:
                            st.error("❌ PDF gagal dibuat atau file terlalu kecil. Cek dependencies dan data.")
                        else:
                            st.download_button(
                                label="📥 Download PDF Report",
                                data=pdf_bytes,
                                file_name="3d_container_packing_multiview.pdf",
                                mime="application/pdf"
                            )
                            st.success("✅ PDF multi-view berhasil dibuat!")
                    except Exception as e:
                        st.error(f"❌ Error membuat PDF: {str(e)}")
                        st.info("Pastikan package kaleido dan reportlab sudah terinstall: pip install kaleido reportlab")
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
        - **Export Data**: Hasil dapat diekspor ke format CSV
        - **📄 Export PDF Multi-View**: Generate laporan PDF dengan 4 sudut pandang berbeda (Front, Side, Top, Isometric)
        
        ### Cara Penggunaan:
        1. Pilih ukuran kontainer atau gunakan custom
        2. Tambahkan barang dengan dimensi dan berat
        3. Gunakan tombol "Sample" untuk mencoba contoh
        4. Klik "Mulai Proses Pengepakan" untuk melihat hasil
        5. Interaksi dengan visualisasi 3D untuk melihat detail
        6. Export hasil ke CSV atau PDF multi-view report
        """)