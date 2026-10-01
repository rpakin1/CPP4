import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Safe import for py3dbp
try:
  from py3dbp import Bin, Item, Packer
except ModuleNotFoundError:
  st.error(
      "❌ **Missing Dependency:** ไม่พบแพ็กเกจ `py3dbp` โปรดติดตั้งโดยรันคำสั่ง"
      " `pip install py3dbp` หรือเพิ่ม `py3dbp` ในไฟล์ `requirements.txt`"
  )
  st.stop()

# ------------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & DATA LOADING
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="3D Container Loading System (py3dbp + LBSz)",
    page_icon="📦",
    layout="wide",
)

COLOR_PALETTE = [
    "#FF5733",
    "#33FF57",
    "#3380FF",
    "#FF33A8",
    "#33FFF3",
    "#F3FF33",
    "#FF8333",
    "#9B59B6",
    "#1ABC9C",
    "#E67E22",
]

CONTAINER_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRFS2SNdgb2nBPQnwkyJRTGf2_9syexHsC3asjnkjhJOStVapomghBi9Ew9g5sYfohVoKVdghKajuCH/pub?gid=0&single=true&output=csv"
BOX_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRFS2SNdgb2nBPQnwkyJRTGf2_9syexHsC3asjnkjhJOStVapomghBi9Ew9g5sYfohVoKVdghKajuCH/pub?gid=1420125949&single=true&output=csv"


@st.cache_data(ttl=5)
def load_master_data():
  try:
    df_c = pd.read_csv(CONTAINER_CSV_URL)
    df_b = pd.read_csv(BOX_CSV_URL)
    return df_c, df_b
  except Exception as e:
    df_c = pd.DataFrame([{
        "Container_ID": "CONT-20",
        "Container_Name": "20ft Dry Box",
        "Width_cm": 235,
        "Length_cm": 590,
        "Height_cm": 239,
        "Max_Weight_kg": 28000,
        "Front_Axle_Limit_kg": 10000,
        "Rear_Axle_Limit_kg": 18000,
        "Kingpin_Distance_cm": 450,
    }])
    df_b = pd.DataFrame([
        {
            "Box_ID": "BOX-A",
            "Box_Name": "Box A (Parts)",
            "Customer_Name": "Supplier A",
            "Width_cm": 40,
            "Length_cm": 50,
            "Height_cm": 30,
            "Weight_kg": 85,
            "LBS_z": 300,
            "Qty": 20,
            "Priority_Level": 2,
            "Color": "#ff7f0e",
        },
        {
            "Box_ID": "BOX-B",
            "Box_Name": "Box B (Tools)",
            "Customer_Name": "Supplier B",
            "Width_cm": 60,
            "Length_cm": 80,
            "Height_cm": 40,
            "Weight_kg": 35,
            "LBS_z": 500,
            "Qty": 15,
            "Priority_Level": 2,
            "Color": "#bcbd22",
        },
        {
            "Box_ID": "BOX-C",
            "Box_Name": "Pallet C (spare)",
            "Customer_Name": "BYD",
            "Width_cm": 90,
            "Length_cm": 115,
            "Height_cm": 120,
            "Weight_kg": 511,
            "LBS_z": 1500,
            "Qty": 10,
            "Priority_Level": 1,
            "Color": "#1f77b4",
        },
        {
            "Box_ID": "BOX-D",
            "Box_Name": "Pallet D (Component)",
            "Customer_Name": "Toyota",
            "Width_cm": 90,
            "Length_cm": 115,
            "Height_cm": 100,
            "Weight_kg": 510,
            "LBS_z": 510,
            "Qty": 8,
            "Priority_Level": 1,
            "Color": "#2ca02c",
        },
    ])
    return df_c, df_b


df_container, df_box = load_master_data()


def assign_box_colors(df_b):
  colors = {}
  for idx, row in df_b.iterrows():
    b_id = row["Box_ID"]
    color = row.get("Color")
    if pd.isna(color) or str(color).strip() == "":
      color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
    colors[b_id] = color
  return colors


box_colors_map = assign_box_colors(df_box)


# ------------------------------------------------------------------------------
# 2. TOP WEIGHT LBSz SAFETY CHECK FOR PY3DBP
# ------------------------------------------------------------------------------
def check_py3dbp_lbsz_safety(candidate_item, candidate_pos, validated_items):
  cx, cy, cz = candidate_pos
  cw, ch, cd = (
      float(candidate_item.width),
      float(candidate_item.height),
      float(candidate_item.depth),
  )

  if cy == 0:
    return True

  all_items = []
  for item in validated_items:
    all_items.append({
        "id": id(item),
        "x1": float(item.position[0]),
        "y1": float(item.position[1]),
        "z1": float(item.position[2]),
        "x2": float(item.position[0]) + float(item.width),
        "y2": float(item.position[1]) + float(item.height),
        "z2": float(item.position[2]) + float(item.depth),
        "weight": float(item.weight),
        "lbs_z": getattr(item, "lbs_z", float("inf")),
    })

  cand_dict = {
      "id": id(candidate_item),
      "x1": cx,
      "y1": cy,
      "z1": cz,
      "x2": cx + cw,
      "y2": cy + ch,
      "z2": cz + cd,
      "weight": float(candidate_item.weight),
      "lbs_z": getattr(candidate_item, "lbs_z", float("inf")),
  }
  all_items.append(cand_dict)

  sorted_items = sorted(all_items, key=lambda i: i["y2"], reverse=True)
  accumulated_loads = {i["id"]: i["weight"] for i in all_items}

  for top_i in sorted_items:
    top_area = (top_i["x2"] - top_i["x1"]) * (top_i["z2"] - top_i["z1"])
    if top_area <= 0:
      continue

    total_top_load = accumulated_loads[top_i["id"]]

    for bot_i in sorted_items:
      if abs(bot_i["y2"] - top_i["y1"]) < 0.1:
        ox = max(
            0, min(top_i["x2"], bot_i["x2"]) - max(top_i["x1"], bot_i["x1"])
        )
        oz = max(
            0, min(top_i["z2"], bot_i["z2"]) - max(top_i["z1"], bot_i["z1"])
        )
        overlap_area = ox * oz

        if overlap_area > 0:
          weight_share = total_top_load * (overlap_area / top_area)
          accumulated_loads[bot_i["id"]] += weight_share

  for item_dict in all_items:
    if item_dict["id"] == id(candidate_item):
      continue

    load_on_box = accumulated_loads[item_dict["id"]] - item_dict["weight"]
    if load_on_box > item_dict["lbs_z"]:
      return False

  return True


# ------------------------------------------------------------------------------
# 3. PACKING ENGINE & LDD CALCULATIONS
# ------------------------------------------------------------------------------
def is_overlapping_3d(item1_pos, item1_dim, item2_pos, item2_dim):
  x1, y1, z1 = item1_pos
  w1, h1, d1 = item1_dim
  x2, y2, z2 = item2_pos
  w2, h2, d2 = item2_dim
  return (
      (x1 < x2 + w2 - 0.1)
      and (x1 + w1 > x2 + 0.1)
      and (y1 < y2 + h2 - 0.1)
      and (y1 + h1 > y2 + 0.1)
      and (z1 < z2 + d2 - 0.1)
      and (z1 + d1 > z2 + 0.1)
  )


def run_py3dbp_packing_engine(
    container_info, user_box_orders, support_surface_ratio=0.85
):
  cw, ch, cl = (
      int(container_info["Width_cm"]),
      int(container_info["Height_cm"]),
      int(container_info["Length_cm"]),
  )
  max_w = float(container_info.get("Max_Weight_kg", 28000))

  order_rows = []
  for item in user_box_orders:
    b = item["info"]
    order_rows.append({
        "Box_ID": b["Box_ID"],
        "Box_Name": b.get("Box_Name", b["Box_ID"]),
        "Customer_Name": b.get("Customer_Name", "N/A"),
        "Width_cm": float(b.get("Width_cm", 0)),
        "Length_cm": float(b.get("Length_cm", 0)),
        "Height_cm": float(b.get("Height_cm", 0)),
        "Weight_kg": float(b.get("Weight_kg", 0)),
        "LBS_z": float(b.get("LBS_z", b.get("lbs_z", float("inf")))),
        "Qty": int(item["qty"]),
        "Priority_Level": int(b.get("Priority_Level", 2)),
        "Color": box_colors_map.get(b["Box_ID"], "#3380FF"),
    })

  box_orders_df = pd.DataFrame(order_rows)
  if box_orders_df.empty:
    return [], []

  box_df_sorted = box_orders_df.sort_values(
      by=["Priority_Level", "Weight_kg"], ascending=[True, False]
  )
  all_fitted_items = []

  for _, row in box_df_sorted.iterrows():
    packer = Packer()
    temp_bin = Bin(
        str(container_info["Container_Name"]), cw, ch, cl, max_w
    )

    for fitted in all_fitted_items:
      fixed_item = Item(
          fitted.name,
          fitted.width,
          fitted.height,
          fitted.depth,
          fitted.weight,
      )
      fixed_item.position = fitted.position
      fixed_item.color = getattr(fitted, "color", "#7f7f7f")
      fixed_item.box_id = getattr(fitted, "box_id", "UNKNOWN")
      fixed_item.box_name = getattr(fitted, "box_name", "UNKNOWN")
      fixed_item.customer_name = getattr(fitted, "customer_name", "UNKNOWN")
      fixed_item.lbs_z = getattr(fitted, "lbs_z", float("inf"))
      temp_bin.items.append(fixed_item)

    packer.add_bin(temp_bin)

    qty = int(row["Qty"])
    for i in range(qty):
      item = Item(
          str(f"{row['Box_Name']} #{i+1}"),
          int(row["Width_cm"]),
          int(row["Height_cm"]),
          int(row["Length_cm"]),
          float(row["Weight_kg"]),
      )
      item.color = str(row["Color"])
      item.box_id = str(row["Box_ID"])
      item.box_name = str(row["Box_Name"])
      item.customer_name = str(row["Customer_Name"])
      item.lbs_z = float(row["LBS_z"])
      packer.add_item(item)

    packer.pack(
        bigger_first=True, distribute_items=False, number_of_decimals=0
    )
    all_fitted_items = packer.bins[0].items

  all_fitted_items.sort(
      key=lambda item: (
          float(item.position[1]),
          float(item.position[2]),
          float(item.position[0]),
      )
  )

  validated_items = []
  for item in all_fitted_items:
    ix, iy, iz = [float(p) for p in item.position]
    iw, ih, id_len = float(item.width), float(item.height), float(item.depth)

    max_underneath_y = 0.0
    supporting_surface_area = 0.0

    for val_item in validated_items:
      vx, vy, vz = [float(p) for p in val_item.position]
      vw, vh, vd = (
          float(val_item.width),
          float(val_item.height),
          float(val_item.depth),
      )

      x_overlap_len = max(0.0, min(ix + iw, vx + vw) - max(ix, vx))
      z_overlap_len = max(0.0, min(iz + id_len, vz + vd) - max(iz, vz))
      overlap_area = x_overlap_len * z_overlap_len

      if overlap_area > 0 and (vy + vh <= iy + 0.1):
        top_y = vy + vh
        if top_y > max_underneath_y:
          max_underneath_y = top_y
          supporting_surface_area = overlap_area

    base_area = iw * id_len
    support_ratio = (
        (supporting_surface_area / base_area) if max_underneath_y > 0 else 1.0
    )

    candidate_pos = [ix, max_underneath_y, iz]
    candidate_dim = [iw, ih, id_len]

    has_collision = False
    for val_item in validated_items:
      val_pos = [float(p) for p in val_item.position]
      val_dim = [
          float(val_item.width),
          float(val_item.height),
          float(val_item.depth),
      ]
      if is_overlapping_3d(candidate_pos, candidate_dim, val_pos, val_dim):
        has_collision = True
        break

    is_lbsz_safe = check_py3dbp_lbsz_safety(
        item, candidate_pos, validated_items
    )

    if (
        not has_collision
        and (support_ratio >= support_surface_ratio)
        and is_lbsz_safe
    ):
      item.position = candidate_pos
      validated_items.append(item)

  placed_boxes = []
  placed_counts = {}

  for item in validated_items:
    x1, y1, z1 = [float(p) for p in item.position]
    bw, bh, bl = float(item.width), float(item.height), float(item.depth)
    b_id = getattr(item, "box_id", "N/A")

    placed_counts[b_id] = placed_counts.get(b_id, 0) + 1
    placed_boxes.append({
        "Box_ID": b_id,
        "Box_Name": getattr(item, "box_name", item.name),
        "Customer_Name": getattr(item, "customer_name", "N/A"),
        "x1": x1,
        "y1": y1,
        "z1": z1,
        "x2": x1 + bw,
        "y2": y1 + bh,
        "z2": z1 + bl,
        "Width_cm": bw,
        "Length_cm": bl,
        "Height_cm": bh,
        "weight_kg": float(item.weight),
        "lbs_z": getattr(item, "lbs_z", "N/A"),
        "color": getattr(item, "color", "#3380FF"),
        "label": (
            f"{getattr(item, 'box_name', item.name)} |"
            f" {getattr(item, 'customer_name', 'N/A')}"
        ),
    })

  unfitted_boxes = []
  for item in user_box_orders:
    b_id = item["info"]["Box_ID"]
    req_qty = item["qty"]
    loaded_qty = placed_counts.get(b_id, 0)
    leftover = req_qty - loaded_qty

    if leftover > 0:
      unfitted_boxes.append({
          "Box_ID": b_id,
          "Box_Name": item["info"].get("Box_Name", b_id),
          "Customer_Name": item["info"].get("Customer_Name", "N/A"),
          "Requested_Qty": req_qty,
          "Unfitted_Qty": leftover,
          "Unit_Weight_kg": float(item["info"].get("Weight_kg", 0)),
      })

  return placed_boxes, unfitted_boxes


def calculate_ldd(placed_boxes, container_info):
  if not placed_boxes:
    return 0, 0, 0, 0, 0, 0, 0, True

  total_weight = 0.0
  moment_x = 0.0
  moment_y = 0.0

  for b in placed_boxes:
    w = b["weight_kg"]
    cx = (b["x1"] + b["x2"]) / 2.0
    cy = (b["z1"] + b["z2"]) / 2.0
    total_weight += w
    moment_x += cx * w
    moment_y += cy * w

  cg_x = moment_x / total_weight if total_weight > 0 else 0
  cg_y = moment_y / total_weight if total_weight > 0 else 0

  wheelbase = float(
      container_info.get(
          "Kingpin_Distance_cm", float(container_info["Length_cm"]) * 0.8
      )
  )
  rear_axle_weight = total_weight * (cg_y / wheelbase) if wheelbase > 0 else 0
  front_axle_weight = total_weight - rear_axle_weight

  f_limit = float(container_info.get("Front_Axle_Limit_kg", 10000))
  r_limit = float(container_info.get("Rear_Axle_Limit_kg", 18000))

  pass_ldd = (front_axle_weight <= f_limit) and (rear_axle_weight <= r_limit)
  return (
      total_weight,
      cg_x,
      cg_y,
      front_axle_weight,
      rear_axle_weight,
      f_limit,
      r_limit,
      pass_ldd,
  )


# ------------------------------------------------------------------------------
# 4. PLOTLY 3D RENDER ENGINE
# ------------------------------------------------------------------------------
def create_3d_cube_mesh(
    x1, y1, z1, x2, y2, z2, color, name_tag, box_details
):
  x = [x1, x2, x2, x1, x1, x2, x2, x1]
  y = [y1, y1, y2, y2, y1, y1, y2, y2]
  z = [z1, z1, z1, z1, z2, z2, z2, z2]
  i = [7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2]
  j = [3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3]
  k = [0, 7, 5, 3, 6, 7, 1, 1, 5, 5, 7, 6]

  hover_text = (
      f"<b>{box_details['Box_Name']}</b><br>"
      f"<b>Customer:</b> {box_details['Customer_Name']}<br>"
      f"------------------------------<br>"
      f"<b>Coord X (Width):</b> {x1:.0f} to {x2:.0f} cm<br>"
      f"<b>Coord Y (Height):</b> {y1:.0f} to {y2:.0f} cm<br>"
      f"<b>Coord Z (Length):</b> {z1:.0f} to {z2:.0f} cm<br>"
      f"------------------------------<br>"
      f"<b>Dimensions:</b> {x2-x1:.0f} x {y2-y1:.0f} x {z2-z1:.0f} cm<br>"
      f"<b>Weight:</b> {box_details['weight_kg']:.1f} kg<br>"
      f"<b>LBSz:</b> {box_details.get('lbs_z', 'N/A')}"
  )

  return go.Mesh3d(
      x=x,
      y=y,
      z=z,
      i=i,
      j=j,
      k=k,
      color=color,
      opacity=0.85,
      name=name_tag,
      hovertext=hover_text,
      hoverinfo="text",
      showscale=False,
  )


def plot_interactive_container(container, placed_boxes, cg_x, cg_y):
  fig = go.Figure()
  cw = float(container["Width_cm"])
  ch = float(container["Height_cm"])
  cl = float(container["Length_cm"])

  fig.add_trace(
      go.Scatter3d(
          x=[0, cw, cw, 0, 0, 0, cw, cw, 0, 0, cw, cw, cw, cw, 0, 0],
          y=[0, 0, ch, ch, 0, 0, 0, ch, ch, 0, 0, 0, ch, ch, ch, ch],
          z=[0, 0, 0, 0, 0, cl, cl, cl, cl, cl, cl, 0, 0, cl, cl, 0],
          mode="lines",
          line=dict(color="black", width=4),
          name=f"Container {container['Container_Name']}",
          hoverinfo="none",
      )
  )

  for b in placed_boxes:
    mesh = create_3d_cube_mesh(
        b["x1"],
        b["y1"],
        b["z1"],
        b["x2"],
        b["y2"],
        b["z2"],
        color=b["color"],
        name_tag=b["label"],
        box_details=b,
    )
    fig.add_trace(mesh)

    fig.add_trace(
        go.Scatter3d(
            x=[
                b["x1"],
                b["x2"],
                b["x2"],
                b["x1"],
                b["x1"],
                b["x1"],
                b["x2"],
                b["x2"],
                b["x1"],
                b["x1"],
                b["x2"],
                b["x2"],
                b["x2"],
                b["x2"],
                b["x1"],
                b["x1"],
            ],
            y=[
                b["y1"],
                b["y1"],
                b["y2"],
                b["y2"],
                b["y1"],
                b["y1"],
                b["y1"],
                b["y2"],
                b["y2"],
                b["y1"],
                b["y1"],
                b["y1"],
                b["y2"],
                b["y2"],
                b["y2"],
                b["y2"],
            ],
            z=[
                b["z1"],
                b["z1"],
                b["z1"],
                b["z1"],
                b["z1"],
                b["z2"],
                b["z2"],
                b["z2"],
                b["z2"],
                b["z2"],
                b["z2"],
                b["z1"],
                b["z1"],
                b["z2"],
                b["z2"],
                b["z1"],
            ],
            mode="lines",
            line=dict(color="rgba(0,0,0,0.6)", width=2),
            showlegend=False,
            hoverinfo="none",
        )
    )

  if placed_boxes:
    fig.add_trace(
        go.Scatter3d(
            x=[cg_x],
            y=[ch / 2],
            z=[cg_y],
            mode="markers",
            marker=dict(size=10, color="red", symbol="diamond"),
            name="Accumulated CG Point",
        )
    )

  fig.update_layout(
      scene=dict(
          xaxis=dict(title="X: Width (cm)", range=[0, cw]),
          yaxis=dict(title="Y: Height (cm)", range=[0, ch]),
          zaxis=dict(title="Z: Length (cm)", range=[0, cl]),
          aspectmode="manual",
          aspectratio=dict(x=cw / cl, y=ch / cl, z=1.0),
          camera=dict(
              eye=dict(x=-1.8, y=1.2, z=0.8), up=dict(x=0, y=1, z=0)
          ),
      ),
      margin=dict(r=0, l=0, b=0, t=10),
      height=650,
      hoverlabel=dict(bgcolor="white", font_size=13, font_family="Arial"),
  )
  return fig


# ------------------------------------------------------------------------------
# 5. STREAMLIT UI LAYOUT & EXECUTION
# ------------------------------------------------------------------------------
tab_user, tab_reports, tab_admin = st.tabs([
    "🚛 User View (3D Loading & LDD)",
    "📊 Reports & Export CSV",
    "⚙️ Admin (Master Data)",
])

st.sidebar.header("📋 Container & Cargo Selection")

if st.sidebar.button(
    "🔄 Refresh Data from Google Sheet",
    use_container_width=True,
    type="primary",
):
  load_master_data.clear()
  st.cache_data.clear()
  st.rerun()

selected_container_name = st.sidebar.selectbox(
    "Select Container Type:", df_container["Container_Name"].unique()
)
container_info = df_container[
    df_container["Container_Name"] == selected_container_name
].iloc[0]

support_surface_ratio = st.sidebar.slider(
    "Support Surface Ratio (Stability Threshold):",
    min_value=0.50,
    max_value=1.00,
    value=0.85,
    step=0.05,
    help="Minimum required percentage of a box's base area supported from below.",
)

st.sidebar.markdown("---")
st.sidebar.subheader("Specify Box Quantities")

user_box_orders = []
for _, box in df_box.iterrows():
  label = f"{box['Box_Name']} [{box.get('Customer_Name', 'N/A')}]"
  default_qty = int(box.get("Qty", box.get("qty", 10)))
  qty = st.sidebar.number_input(
      label, min_value=0, value=default_qty, step=1, key=f"qty_{box['Box_ID']}"
  )
  if qty > 0:
    user_box_orders.append({"info": box, "qty": qty})

# RUN ENGINE
placed_boxes, unfitted_boxes = run_py3dbp_packing_engine(
    container_info, user_box_orders, support_surface_ratio=support_surface_ratio
)
tot_w, cg_x, cg_y, f_axle, r_axle, f_limit, r_limit, ldd_pass = calculate_ldd(
    placed_boxes, container_info
)

# --- TAB 1: USER VIEW ---
with tab_user:
  st.title("📦 3D Container Loading & LDD Analysis (py3dbp Engine)")

  container_vol = (
      float(container_info["Width_cm"])
      * float(container_info["Length_cm"])
      * float(container_info["Height_cm"])
  )
  used_vol = sum(
      (b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) * (b["z2"] - b["z1"])
      for b in placed_boxes
  )
  vol_utilization = (
      (used_vol / container_vol) * 100 if container_vol > 0 else 0
  )
  max_c_w = float(container_info.get("Max_Weight_kg", 28000))
  weight_utilization = (tot_w / max_c_w) * 100 if max_c_w > 0 else 0

  m1, m2, m3, m4 = st.columns(4)
  m1.metric("📦 Volume Util.", f"{vol_utilization:.2f} %")
  m2.metric(
      "⚖️ Total Weight",
      f"{tot_w:,.1f} kg",
      f"Limit {max_c_w:,.0f} kg ({weight_utilization:.1f}%)",
  )
  m3.metric("🎯 CG Point (X, Z)", f"{cg_x:.0f}, {cg_y:.0f} cm")
  m4.metric("🚛 LDD Status", "✅ Safe" if ldd_pass else "⚠️ Overload")

  st.markdown("---")

  col_graph, col_legend = st.columns([3.8, 1.2])
  with col_graph:
    fig = plot_interactive_container(container_info, placed_boxes, cg_x, cg_y)
    st.plotly_chart(fig, use_container_width=True)

  with col_legend:
    st.subheader("🎨 Color Legend & Summary")

    loaded_counts = {}
    for b in placed_boxes:
      b_id = b["Box_ID"]
      loaded_counts[b_id] = loaded_counts.get(b_id, 0) + 1

    for item in user_box_orders:
      box = item["info"]
      b_id = box["Box_ID"]
      requested_qty = item["qty"]
      loaded_qty = loaded_counts.get(b_id, 0)
      color = box_colors_map.get(b_id, "#FF5733")

      badge_bg = (
          "#2ECC71"
          if loaded_qty == requested_qty
          else ("#E67E22" if loaded_qty > 0 else "#E74C3C")
      )

      st.markdown(
          f"""
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; padding: 8px; border-radius: 6px; background-color: #F8F9FA; border: 1px solid #E9ECEF;">
                <div style="display: flex; align-items: center;">
                    <div style="width: 18px; height: 18px; background-color: {color}; border-radius: 4px; margin-right: 10px;"></div>
                    <div>
                        <span style="font-size: 13px; font-weight: 600; color: #212529;">{box.get('Box_Name', b_id)}</span><br>
                        <small style="color: #6C757D;">{box.get('Customer_Name', 'N/A')}</small>
                    </div>
                </div>
                <div>
                    <span style="background-color: {badge_bg}; color: white; padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 12px;">
                        {loaded_qty}/{requested_qty}
                    </span>
                </div>
            </div>
            """,
          unsafe_allow_html=True,
      )

# --- TAB 2: REPORTS ---
with tab_reports:
  st.title("📊 Loading Summary & CSV Export")
  st.subheader("⚠️ 1. Unfitted Boxes Report")
  if unfitted_boxes:
    df_unfitted = pd.DataFrame(unfitted_boxes)
    st.warning(
        f"Found {sum(b['Unfitted_Qty'] for b in unfitted_boxes)} box(es) that"
        " could not fit into the container."
    )
    st.dataframe(df_unfitted, use_container_width=True)

    csv_unfitted = df_unfitted.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📥 Download Unfitted Boxes Report (CSV)",
        data=csv_unfitted,
        file_name="unfitted_boxes_report.csv",
        mime="text/csv",
    )
  else:
    st.success("🎉 All requested boxes have been placed successfully!")

  st.markdown("---")
  st.subheader("📍 2. Placed Boxes 3D Coordinates")
  if placed_boxes:
    df_placed = pd.DataFrame(placed_boxes)
    display_cols = [
        "Box_ID",
        "Box_Name",
        "Customer_Name",
        "x1",
        "y1",
        "z1",
        "x2",
        "y2",
        "z2",
        "Width_cm",
        "Length_cm",
        "Height_cm",
        "weight_kg",
        "lbs_z",
    ]
    df_placed_display = df_placed[display_cols]

    st.write(f"Total placed boxes: **{len(placed_boxes)}** units.")
    st.dataframe(df_placed_display, use_container_width=True)

    csv_placed = df_placed_display.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📥 Download 3D Placement Coordinates (CSV)",
        data=csv_placed,
        file_name="placed_boxes_positions.csv",
        mime="text/csv",
    )

# --- TAB 3: ADMIN ---
with tab_admin:
  st.title("⚙️ Master Data (Google Sheets Real-Time)")
  st.caption("Live data read directly from Google Sheets.")
  st.subheader("1. Container Master Table")
  st.dataframe(df_container, use_container_width=True)
  st.subheader("2. Box Master Table")
  st.dataframe(df_box, use_container_width=True)
