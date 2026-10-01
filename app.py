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
        'id': id(item),
        'x1': float(item.position[0]),
        'y1': float(item.position[1]),
        'z1': float(item.position[2]),
        'x2': float(item.position[0]) + float(item.width),
        'y2': float(item.position[1]) + float(item.height),
        'z2': float(item.position[2]) + float(item.depth),
        'weight': float(item.weight),
        'lbs_z': getattr(item, 'lbs_z', float('inf')),
    })

  cand_dict = {
      'id': id(candidate_item),
      'x1': cx,
      'y1': cy,
      'z1': cz,
      'x2': cx + cw,
      'y2': cy + ch,
      'z2': cz + cd,
      'weight': float(candidate_item.weight),
      'lbs_z': getattr(candidate_item, 'lbs_z', float('inf')),
  }
  all_items.append(cand_dict)

  sorted_items = sorted(all_items, key=lambda i: i['y2'], reverse=True)
  accumulated_loads = {i['id']: i['weight'] for i in all_items}

  for top_i in sorted_items:
    top_area = (top_i['x2'] - top_i['x1']) * (top_i['z2'] - top_i['z1'])
    if top_area <= 0:
      continue

    total_top_load = accumulated_loads[top_i['id']]

    for bot_i in sorted_items:
      if abs(bot_i['y2'] - top_i['y1']) < 0.1:
        ox = max(
            0, min(top_i['x2'], bot_i['x2']) - max(top_i['x1'], bot_i['x1'])
        )
        oz = max(
            0, min(top_i['z2'], bot_i['z2']) - max(top_i['z1'], bot_i['z1'])
        )
        overlap_area = ox * oz

        if overlap_area > 0:
          weight_share = total_top_load * (overlap_area / top_area)
          accumulated_loads[bot_i['id']] += weight_share

  for item_dict in all_items:
    if item_dict['id'] == id(candidate_item):
      continue

    load_on_box = accumulated_loads[item_dict['id']] - item_dict['weight']
    if load_on_box > item_dict['lbs_z']:
      return False

  return True


# ------------------------------------------------------------------------------
# 3. PACKING ENGINE & INTERFACE
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
      int(container_info['Width_cm']),
      int(container_info['Height_cm']),
      int(container_info['Length_cm']),
  )
  max_w = float(container_info.get('Max_Weight_kg', 28000))

  order_rows = []
  for item in user_box_orders:
    b = item['info']
    order_rows.append({
        'Box_ID': b['Box_ID'],
        'Box_Name': b.get('Box_Name', b['Box_ID']),
        'Customer_Name': b.get('Customer_Name', 'N/A'),
        'Width_cm': float(b.get('Width_cm', 0)),
        'Length_cm': float(b.get('Length_cm', 0)),
        'Height_cm': float(b.get('Height_cm', 0)),
        'Weight_kg': float(b.get('Weight_kg', 0)),
        'LBS_z': float(b.get('LBS_z', b.get('lbs_z', float('inf')))),
        'Qty': int(item['qty']),
        'Priority_Level': int(b.get('Priority_Level', 2)),
        'Color': b.get('Color', '#3380FF'),
    })

  box_orders_df = pd.DataFrame(order_rows)
  if box_orders_df.empty:
    return [], []

  box_df_sorted = box_orders_df.sort_values(
      by=['Priority_Level', 'Weight_kg'], ascending=[True, False]
  )
  all_fitted_items = []

  for _, row in box_df_sorted.iterrows():
    packer = Packer()
    temp_bin = Bin(
        str(container_info['Container_Name']), cw, ch, cl, max_w
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
      fixed_item.color = getattr(fitted, 'color', '#7f7f7f')
      fixed_item.box_id = getattr(fitted, 'box_id', 'UNKNOWN')
      fixed_item.box_name = getattr(fitted, 'box_name', 'UNKNOWN')
      fixed_item.customer_name = getattr(fitted, 'customer_name', 'UNKNOWN')
      fixed_item.lbs_z = getattr(fitted, 'lbs_z', float('inf'))
      temp_bin.items.append(fixed_item)

    packer.add_bin(temp_bin)

    qty = int(row['Qty'])
    for i in range(qty):
      item = Item(
          str(f"{row['Box_Name']} #{i+1}"),
          int(row['Width_cm']),
          int(row['Height_cm']),
          int(row['Length_cm']),
          float(row['Weight_kg']),
      )
      item.color = str(row['Color'])
      item.box_id = str(row['Box_ID'])
      item.box_name = str(row['Box_Name'])
      item.customer_name = str(row['Customer_Name'])
      item.lbs_z = float(row['LBS_z'])
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

    # Check Top Weight LBSz constraint
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
    b_id = getattr(item, 'box_id', 'N/A')

    placed_counts[b_id] = placed_counts.get(b_id, 0) + 1
    placed_boxes.append({
        'Box_ID': b_id,
        'Box_Name': getattr(item, 'box_name', item.name),
        'Customer_Name': getattr(item, 'customer_name', 'N/A'),
        'x1': x1,
        'y1': y1,
        'z1': z1,
        'x2': x1 + bw,
        'y2': y1 + bh,
        'z2': z1 + bl,
        'Width_cm': bw,
        'Length_cm': bl,
        'Height_cm': bh,
        'weight_kg': float(item.weight),
        'lbs_z': getattr(item, 'lbs_z', 'N/A'),
        'color': getattr(item, 'color', '#3380FF'),
        'label': (
            f"{getattr(item, 'box_name', item.name)} |"
            f" {getattr(item, 'customer_name', 'N/A')}"
        ),
    })

  unfitted_boxes = []
  for item in user_box_orders:
    b_id = item['info']['Box_ID']
    req_qty = item['qty']
    loaded_qty = placed_counts.get(b_id, 0)
    leftover = req_qty - loaded_qty

    if leftover > 0:
      unfitted_boxes.append({
          'Box_ID': b_id,
          'Box_Name': item['info'].get('Box_Name', b_id),
          'Customer_Name': item['info'].get('Customer_Name', 'N/A'),
          'Requested_Qty': req_qty,
          'Unfitted_Qty': leftover,
          'Unit_Weight_kg': float(item['info'].get('Weight_kg', 0)),
      })

  return placed_boxes, unfitted_boxes
