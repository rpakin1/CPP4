import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ------------------------------------------------------------------------------
# 1. PAGE CONFIGURATION
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="3D Container Loading System", page_icon="📦", layout="wide"
)

# ------------------------------------------------------------------------------
# 2. DYNAMIC COLOR GENERATOR
# ------------------------------------------------------------------------------
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
    "#8E44AD",
    "#2ECC71",
    "#D35400",
    "#C0392B",
    "#16A085",
]


def assign_box_colors(df_box):
  box_colors = {}
  if not df_box.empty and "Box_ID" in df_box.columns:
    for idx, row in df_box.iterrows():
      box_id = row["Box_ID"]
      color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
      box_colors[box_id] = color
  return box_colors


# ------------------------------------------------------------------------------
# 3. CORE EMPTY SPACE & MAXIMAL MERGING ENGINE (L-SHAPE & OVERLAP SUPPORT)
# ------------------------------------------------------------------------------
class EmptySpace:

  def __init__(
      self,
      x1,
      y1,
      z1,
      x2,
      y2,
      z2,
      lbs_z_limit=float("inf"),
      base_lbs_density=float("inf"),
  ):
    self.x1, self.y1, self.z1 = x1, y1, z1
    self.x2, self.y2, self.z2 = x2, y2, z2
    self.width = max(0.0, x2 - x1)
    self.length = max(0.0, y2 - y1)
    self.height = max(0.0, z2 - z1)
    self.lbs_z = lbs_z_limit
    self.base_lbs_density = base_lbs_density


def remove_dominated_spaces(space_list):
  """ลบพื้นที่ว่างย่อยที่ถูกพื้นที่ว่างอื่นที่มีขนาดใหญ่กว่าครอบไว้ 100% (Non-Dominated Filtering)"""
  filtered_spaces = []
  for i, s1 in enumerate(space_list):
    is_dominated = False
    for j, s2 in enumerate(space_list):
      if i != j:
        # เช็กว่า s1 ซ่อนอยู่ภายใน s2 ทั้งหมดหรือไม่
        if (
            s2.x1 <= s1.x1 + 0.01
            and s2.x2 >= s1.x2 - 0.01
            and s2.y1 <= s1.y1 + 0.01
            and s2.y2 >= s1.y2 - 0.01
            and s2.z1 <= s1.z1 + 0.01
            and s2.z2 >= s1.z2 - 0.01
        ):
          is_dominated = True
          break
    if not is_dominated:
      filtered_spaces.append(s1)
  return filtered_spaces


def generate_maximal_empty_spaces(space_list):
  """สร้าง Maximal Empty Spaces (MES) เพื่อรองรับพื้นที่ L-Shape และการวางคร่อมซ้อนทับบางส่วน"""
  if len(space_list) <= 1:
    return space_list

  maximal_spaces = list(space_list)
  added_new = True

  while added_new:
    added_new = False
    new_candidates = []

    for i in range(len(maximal_spaces)):
      for j in range(i + 1, len(maximal_spaces)):
        s1 = maximal_spaces[i]
        s2 = maximal_spaces[j]

        # รวมเฉพาะพื้นที่ที่อยู่ระดับความสูงเดียวกัน (Z เดียวกัน)
        if abs(s1.z1 - s2.z1) < 0.1 and abs(s1.z2 - s2.z2) < 0.1:
          ox = max(0, min(s1.x2, s2.x2) - max(s1.x1, s2.x1))
          oy = max(0, min(s1.y2, s2.y2) - max(s1.y1, s2.y1))

          # ถ้าพื้นที่แตะกันหรือซ้อนทับกัน (เกิด L-Shape)
          if (
              ox > 0 or oy > 0 or abs(s1.x2 - s2.x1) < 0.1 or abs(s1.y2 - s2.y1) < 0.1
          ):
            # สร้าง Maximal Space แนว X (ขยายความกว้างเต็มขอบ)
            if max(s1.y1, s2.y1) < min(s1.y2, s2.y2):
              mx_space = EmptySpace(
                  min(s1.x1, s2.x1),
                  max(s1.y1, s2.y1),
                  s1.z1,
                  max(s1.x2, s2.x2),
                  min(s1.y2, s2.y2),
                  s1.z2,
                  lbs_z_limit=min(s1.lbs_z, s2.lbs_z),
                  base_lbs_density=min(
                      s1.base_lbs_density, s2.base_lbs_density
                  ),
              )
              if mx_space.width > 0 and mx_space.length > 0:
                new_candidates.append(mx_space)

            # สร้าง Maximal Space แนว Y (ขยายความยาวเต็มขอบ)
            if max(s1.x1, s2.x1) < min(s1.x2, s2.x2):
              my_space = EmptySpace(
                  max(s1.x1, s2.x1),
                  min(s1.y1, s2.y1),
                  s1.z1,
                  min(s1.x2, s2.x2),
                  max(s1.y2, s2.y2),
                  s1.z2,
                  lbs_z_limit=min(s1.lbs_z, s2.lbs_z),
                  base_lbs_density=min(
                      s1.base_lbs_density, s2.base_lbs_density
                  ),
              )
              if my_space.width > 0 and my_space.length > 0:
                new_candidates.append(my_space)

    if new_candidates:
      before_count = len(maximal_spaces)
      maximal_spaces = remove_dominated_spaces(maximal_spaces + new_candidates)
      if len(maximal_spaces) > before_count:
        added_new = True

  return remove_dominated_spaces(maximal_spaces)


def cut_overlapping_spaces(space_list, new_box):
  """เมื่อมีการวางกล่องใหม่ ให้ตัดพื้นที่ว่างใน space_list ที่ทับซ้อนกับกล่องใหม่ออกทันที (Difference Engine)"""
  bx1, by1, bz1 = new_box["x1"], new_box["y1"], new_box["z1"]
  bx2, by2, bz2 = new_box["x2"], new_box["y2"], new_box["z2"]

  updated_spaces = []

  for s in space_list:
    # เช็กว่าทับซ้อนกับกล่องใหม่ใน 3D หรือไม่
    ox = max(0, min(s.x2, bx2) - max(s.x1, bx1))
    oy = max(0, min(s.y2, by2) - max(s.y1, by1))
    oz = max(0, min(s.z2, bz2) - max(s.z1, bz1))

    if ox > 0 and oy > 0 and oz > 0:
      # เกิดการทับซ้อน -> แตกพื้นที่ว่างเดิมออกเป็นพื้นที่ย่อยรอบๆ กล่องใหม่
      if s.x1 < bx1:
        updated_spaces.append(
            EmptySpace(
                s.x1,
                s.y1,
                s.z1,
                bx1,
                s.y2,
                s.z2,
                s.lbs_z,
                s.base_lbs_density,
            )
        )
      if s.x2 > bx2:
        updated_spaces.append(
            EmptySpace(
                bx2,
                s.y1,
                s.z1,
                s.x2,
                s.y2,
                s.z2,
                s.lbs_z,
                s.base_lbs_density,
            )
        )
      if s.y1 < by1:
        updated_spaces.append(
            EmptySpace(
                s.x1,
                s.y1,
                s.z1,
                s.x2,
                by1,
                s.z2,
                s.lbs_z,
                s.base_lbs_density,
            )
        )
      if s.y2 > by2:
        updated_spaces.append(
            EmptySpace(
                s.x1,
                by2,
                s.z1,
                s.x2,
                s.y2,
                s.z2,
                s.lbs_z,
                s.base_lbs_density,
            )
        )
      if s.z1 < bz1:
        updated_spaces.append(
            EmptySpace(
                s.x1,
                s.y1,
                s.z1,
                s.x2,
                s.y2,
                bz1,
                s.lbs_z,
                s.base_lbs_density,
            )
        )
      if s.z2 > bz2:
        updated_spaces.append(
            EmptySpace(
                s.x1,
                s.y1,
                bz2,
                s.x2,
                s.y2,
                s.z2,
                s.lbs_z,
                s.base_lbs_density,
            )
        )
    else:
      updated_spaces.append(s)

  return remove_dominated_spaces(updated_spaces)


# ------------------------------------------------------------------------------
# 4. CORE SAFETY CHECKS (FLAT BASE & CASCADING MULTI-LAYER LBSz)
# ------------------------------------------------------------------------------
def has_flat_and_solid_base(x1, y1, z1, bw, bl, placed_boxes):
  if z1 == 0:
    return True

  x2 = x1 + bw
  y2 = y1 + bl
  candidate_area = bw * bl
  if candidate_area <= 0:
    return False

  supported_area = 0.0
  for pb in placed_boxes:
    if abs(pb["z2"] - z1) < 0.1:
      ox = max(0, min(x2, pb["x2"]) - max(x1, pb["x1"]))
      oy = max(0, min(y2, pb["y2"]) - max(y1, pb["y1"]))
      if ox > 0 and oy > 0:
        supported_area += ox * oy

  return (supported_area / candidate_area) >= 0.999


def check_multi_layer_cascade_lbsz(
    candidate_x1,
    candidate_y1,
    candidate_z1,
    candidate_bw,
    candidate_bl,
    candidate_bh,
    candidate_weight,
    placed_boxes,
):
  if candidate_z1 == 0:
    return True

  candidate_box = {
      "x1": candidate_x1,
      "y1": candidate_y1,
      "z1": candidate_z1,
      "x2": candidate_x1 + candidate_bw,
      "y2": candidate_y1 + candidate_bl,
      "z2": candidate_z1 + candidate_bh,
      "weight_kg": candidate_weight,
      "lbs_z": float("inf"),
  }

  all_boxes = placed_boxes + [candidate_box]
  sorted_boxes = sorted(all_boxes, key=lambda b: b["z2"], reverse=True)
  accumulated_loads = {id(b): b["weight_kg"] for b in all_boxes}

  for top_b in sorted_boxes:
    top_area = (top_b["x2"] - top_b["x1"]) * (top_b["y2"] - top_b["y1"])
    if top_area <= 0:
      continue

    total_top_load = accumulated_loads[id(top_b)]
    under_boxes = []
    total_overlap_area = 0.0

    for bot_b in sorted_boxes:
      if abs(bot_b["z2"] - top_b["z1"]) < 0.1:
        ox = max(0, min(top_b["x2"], bot_b["x2"]) - max(top_b["x1"], bot_b["x1"]))
        oy = max(0, min(top_b["y2"], bot_b["y2"]) - max(top_b["y1"], bot_b["y1"]))
        overlap = ox * oy
        if overlap > 0:
          under_boxes.append((bot_b, overlap))
          total_overlap_area += overlap

    if total_overlap_area > 0:
      for bot_b, overlap in under_boxes:
        weight_share = total_top_load * (overlap / top_area)
        accumulated_loads[id(bot_b)] += weight_share

  for b in placed_boxes:
    raw_lbs = b.get("lbs_z", float("inf"))
    try:
      b_lbs_z = (
          float(raw_lbs)
          if pd.notna(raw_lbs) and str(raw_lbs).strip() != ""
          else float("inf")
      )
    except ValueError:
      b_lbs_z = float("inf")

    load_on_b = accumulated_loads[id(b)] - b["weight_kg"]
    if load_on_b > b_lbs_z:
      return False

  return True


# ------------------------------------------------------------------------------
# 5. CORE DBL ALGORITHM WITH MAXIMAL EMPTY SPACE (MES) ENGINE
# ------------------------------------------------------------------------------
def run_dbl_algorithm(container_info, user_box_orders, box_colors_map):
  cw = container_info["Width_cm"]
  cl = container_info["Length_cm"]
  ch = container_info["Height_cm"]
  max_c_weight = container_info.get("Max_Weight_kg", 28000)

  space_list = [
      EmptySpace(
          0,
          0,
          0,
          cw,
          cl,
          ch,
          lbs_z_limit=max_c_weight,
          base_lbs_density=float("inf"),
      )
  ]
  placed_boxes = []

  boxes_in_stock = {
      item["info"]["Box_ID"]: item["qty"] for item in user_box_orders
  }
  box_info_dict = {
      item["info"]["Box_ID"]: item["info"] for item in user_box_orders
  }

  def get_box_sort_key(item):
    b = item["info"]
    vol = (
        float(b.get("Width_cm", 0))
        * float(b.get("Length_cm", 0))
        * float(b.get("Height_cm", 0))
    )
    raw_lbs = b.get("LBS_z", b.get("lbs_z", 0))
    try:
      lbs_z = float(raw_lbs) if pd.notna(raw_lbs) and str(raw_lbs).strip() != "" else 0
    except ValueError:
      lbs_z = 0
    return (vol, lbs_z)

  sorted_user_orders = sorted(
      user_box_orders, key=get_box_sort_key, reverse=True
  )

  while space_list and any(qty > 0 for qty in boxes_in_stock.values()):
    # เรียงลำดับพื้นที่: ถมกว้าง X -> ยาว Y -> สูง Z
    space_list.sort(key=lambda s: (s.x1, s.y1, s.z1))
    space = space_list.pop(0)

    best_fit = float("inf")
    best_placement = None

    for item in sorted_user_orders:
      box_id = item["info"]["Box_ID"]
      qty_left = boxes_in_stock[box_id]

      if qty_left <= 0:
        continue

      box = box_info_dict[box_id]
      unit_weight = float(box.get("Weight_kg", 0))

      raw_lbs = box.get("LBS_z", box.get("lbs_z", float("inf")))
      try:
        lbs_z_total = (
            float(raw_lbs)
            if pd.notna(raw_lbs) and str(raw_lbs).strip() != ""
            else float("inf")
        )
      except ValueError:
        lbs_z_total = float("inf")

      rotations = [
          (box["Width_cm"], box["Length_cm"], box["Height_cm"], 1),
          (
              (box["Length_cm"], box["Width_cm"], box["Height_cm"], 2)
              if box.get("Allow_Z", 1)
              else None
          ),
          (
              (box["Width_cm"], box["Height_cm"], box["Length_cm"], 3)
              if box.get("Allow_X", 0)
              else None
          ),
          (
              (box["Height_cm"], box["Length_cm"], box["Width_cm"], 4)
              if box.get("Allow_Y", 0)
              else None
          ),
          (
              (box["Length_cm"], box["Height_cm"], box["Width_cm"], 5)
              if (box.get("Allow_Z", 1) and box.get("Allow_X", 0))
              else None
          ),
          (
              (box["Height_cm"], box["Width_cm"], box["Length_cm"], 6)
              if (box.get("Allow_Z", 1) and box.get("Allow_Y", 0))
              else None
          ),
      ]

      for rot in filter(None, rotations):
        bw, bl, bh, rot_id = rot

        if bw > space.width or bl > space.length or bh > space.height:
          continue

        if unit_weight > 0 and unit_weight > space.lbs_z:
          continue

        box_footprint_area = bw * bl
        if box_footprint_area > 0 and unit_weight > 0:
          upper_weight_density = unit_weight / box_footprint_area
          if upper_weight_density > space.base_lbs_density:
            continue

        if not has_flat_and_solid_base(
            space.x1, space.y1, space.z1, bw, bl, placed_boxes
        ):
          continue

        if not check_multi_layer_cascade_lbsz(
            space.x1,
            space.y1,
            space.z1,
            bw,
            bl,
            bh,
            unit_weight,
            placed_boxes,
        ):
          continue

        fit_x = space.width - bw
        fit_y = space.length - bl
        fit_z = space.height - bh
        fit_total = fit_x + fit_y + fit_z

        if fit_total < best_fit:
          best_fit = fit_total
          best_placement = {
              "box_id": box_id,
              "box_info": box,
              "bw": bw,
              "bl": bl,
              "bh": bh,
              "lbs_z_total": lbs_z_total,
              "unit_weight": unit_weight,
          }

    if best_placement:
      bp = best_placement
      b_info = bp["box_info"]
      bw, bl, bh = bp["bw"], bp["bl"], bp["bh"]

      box_color = box_colors_map.get(bp["box_id"], "#3380FF")

      x1, y1, z1 = space.x1, space.y1, space.z1
      new_placed_box = {
          "Box_ID": bp["box_id"],
          "Box_Name": b_info["Box_Name"],
          "Customer_Name": b_info["Customer_Name"],
          "x1": x1,
          "y1": y1,
          "z1": z1,
          "x2": x1 + bw,
          "y2": y1 + bl,
          "z2": z1 + bh,
          "Width_cm": bw,
          "Length_cm": bl,
          "Height_cm": bh,
          "weight_kg": b_info.get("Weight_kg", 0),
          "lbs_z": b_info.get("LBS_z", "N/A"),
          "color": box_color,
          "label": f"{b_info['Box_Name']} | {b_info['Customer_Name']}",
      }

      placed_boxes.append(new_placed_box)
      boxes_in_stock[bp["box_id"]] -= 1

      # 1. ตัดพื้นที่ว่างเดิมที่โดนกล่องใหม่วางทับออกทันที (Difference Engine)
      space_list = cut_overlapping_spaces(space_list, new_placed_box)

      # 2. สร้าง Space B, D, C ใหม่จากการวางกล่องใหม่นี้
      if x1 + bw < space.x2:
        space_list.append(
            EmptySpace(
                x1 + bw,
                y1,
                z1,
                space.x2,
                space.y2,
                space.z2,
                space.lbs_z,
                space.base_lbs_density,
            )
        )

      if y1 + bl < space.y2:
        space_list.append(
            EmptySpace(
                x1,
                y1 + bl,
                z1,
                x1 + bw,
                space.y2,
                space.z2,
                space.lbs_z,
                space.base_lbs_density,
            )
        )

      if z1 + bh < space.z2:
        upper_space_lbs = min(
            space.lbs_z - bp["unit_weight"], bp["lbs_z_total"]
        )
        base_footprint_area = bw * bl
        current_base_density = (
            (bp["lbs_z_total"] / base_footprint_area)
            if base_footprint_area > 0 and bp["lbs_z_total"] < float("inf")
            else float("inf")
        )

        if upper_space_lbs > 0:
          space_list.append(
              EmptySpace(
                  x1,
                  y1,
                  z1 + bh,
                  x1 + bw,
                  y1 + bl,
                  space.z2,
                  lbs_z_limit=upper_space_lbs,
                  base_lbs_density=min(
                      space.base_lbs_density, current_base_density
                  ),
              )
          )

      # 3. หลอมรวมพื้นที่ว่างเป็น Maximal Empty Spaces ( MES Engine สำหรับ L-Shape )
      space_list = generate_maximal_empty_spaces(space_list)

  unfitted_boxes = []
  for item in user_box_orders:
    b_id = item["info"]["Box_ID"]
    leftover = boxes_in_stock[b_id]
    if leftover > 0:
      unfitted_boxes.append({
          "Box_ID": b_id,
          "Box_Name": item["info"]["Box_Name"],
          "Customer_Name": item["info"]["Customer_Name"],
          "Requested_Qty": item["qty"],
          "Unfitted_Qty": leftover,
          "Unit_Weight_kg": item["info"].get("Weight_kg", 0),
      })

  return placed_boxes, unfitted_boxes


# ------------------------------------------------------------------------------
# 6. LDD CALCULATION FUNCTION
# ------------------------------------------------------------------------------
def calculate_ldd(placed_boxes, container_info):
  if not placed_boxes:
    return 0, 0, 0, 0, 0, 0, 0, True

  total_weight = 0.0
  moment_x = 0.0
  moment_y = 0.0

  for b in placed_boxes:
    w = b["weight_kg"]
    cx = (b["x1"] + b["x2"]) / 2.0
    cy = (b["y1"] + b["y2"]) / 2.0
    total_weight += w
    moment_x += cx * w
    moment_y += cy * w

  cg_x = moment_x / total_weight if total_weight > 0 else 0
  cg_y = moment_y / total_weight if total_weight > 0 else 0

  wheelbase = container_info.get(
      "Kingpin_Distance_cm", container_info["Length_cm"] * 0.8
  )
  rear_axle_weight = total_weight * (cg_y / wheelbase) if wheelbase > 0 else 0
  front_axle_weight = total_weight - rear_axle_weight

  f_limit = container_info.get("Front_Axle_Limit_kg", 10000)
  r_limit = container_info.get("Rear_Axle_Limit_kg", 18000)

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
# 7. PLOTLY 3D RENDER ENGINE
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
      f"<b>Coord X:</b> {x1:.0f} to {x2:.0f} cm<br>"
      f"<b>Coord Y:</b> {y1:.0f} to {y2:.0f} cm<br>"
      f"<b>Coord Z:</b> {z1:.0f} to {z2:.0f} cm<br>"
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
  cw, cl, ch = (
      container["Width_cm"],
      container["Length_cm"],
      container["Height_cm"],
  )

  fig.add_trace(
      go.Scatter3d(
          x=[0, cw, cw, 0, 0, 0, cw, cw, 0, 0, cw, cw, cw, cw, 0, 0],
          y=[0, 0, cl, cl, 0, 0, 0, cl, cl, 0, 0, 0, cl, cl, cl, cl],
          z=[0, 0, 0, 0, 0, ch, ch, ch, ch, ch, ch, 0, 0, ch, ch, 0],
          mode="lines",
          line=dict(color="black", width=4),
          name=f"Container {container['Container_Name']}",
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

  if placed_boxes:
    fig.add_trace(
        go.Scatter3d(
            x=[cg_x],
            y=[cg_y],
            z=[ch / 2],
            mode="markers",
            marker=dict(size=10, color="red", symbol="diamond"),
            name="Accumulated CG Point",
        )
    )

  fig.update_layout(
      scene=dict(
          xaxis=dict(title="X: Width (cm)", range=[0, cw]),
          yaxis=dict(title="Y: Length (cm)", range=[0, cl]),
          zaxis=dict(title="Z: Height (cm)", range=[0, ch]),
          aspectmode="data",
      ),
      margin=dict(r=0, l=0, b=0, t=10),
      height=650,
      hoverlabel=dict(bgcolor="white", font_size=13, font_family="Arial"),
  )
  return fig


# ------------------------------------------------------------------------------
# 8. READ MASTER DATA FROM GOOGLE SHEETS
# ------------------------------------------------------------------------------
CONTAINER_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRFS2SNdgb2nBPQnwkyJRTGf2_9syexHsC3asjnkjhJOStVapomghBi9Ew9g5sYfohVoKVdghKajuCH/pub?gid=0&single=true&output=csv"
BOX_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRFS2SNdgb2nBPQnwkyJRTGf2_9syexHsC3asjnkjhJOStVapomghBi9Ew9g5sYfohVoKVdghKajuCH/pub?gid=1420125949&single=true&output=csv"


@st.cache_data(ttl=5)
def load_master_data():
  try:
    df_c = pd.read_csv(CONTAINER_CSV_URL)
    df_b = pd.read_csv(BOX_CSV_URL)
    return df_c, df_b
  except Exception:
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
            "Customer_Name": "Somchai",
            "Width_cm": 40,
            "Length_cm": 50,
            "Height_cm": 30,
            "Weight_kg": 85.0,
            "Allow_X": 0,
            "Allow_Y": 0,
            "Allow_Z": 1,
            "LBS_z": 300,
        },
        {
            "Box_ID": "BOX-B",
            "Box_Name": "Box B (Equipment)",
            "Customer_Name": "Somying",
            "Width_cm": 60,
            "Length_cm": 80,
            "Height_cm": 40,
            "Weight_kg": 35.0,
            "Allow_X": 1,
            "Allow_Y": 1,
            "Allow_Z": 1,
            "LBS_z": 500,
        },
        {
            "Box_ID": "BOX-C",
            "Box_Name": "Pallet C (spare)",
            "Customer_Name": "BYD",
            "Width_cm": 90,
            "Length_cm": 115,
            "Height_cm": 120,
            "Weight_kg": 510.0,
            "Allow_X": 0,
            "Allow_Y": 0,
            "Allow_Z": 1,
            "LBS_z": 1500,
        },
        {
            "Box_ID": "BOX-D",
            "Box_Name": "Pallet D (Component)",
            "Customer_Name": "Toyota",
            "Width_cm": 90,
            "Length_cm": 115,
            "Height_cm": 100,
            "Weight_kg": 510.0,
            "Allow_X": 0,
            "Allow_Y": 0,
            "Allow_Z": 1,
            "LBS_z": 300,
        },
    ])
    return df_c, df_b


df_container, df_box = load_master_data()
box_colors_map = assign_box_colors(df_box)

# ------------------------------------------------------------------------------
# 9. APP MAIN INTERFACE
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

st.sidebar.markdown("---")
st.sidebar.subheader("Specify Box Quantities")

user_box_orders = []
for _, box in df_box.iterrows():
  label = f"{box['Box_Name']} [{box['Customer_Name']}]"
  qty = st.sidebar.number_input(label, min_value=0, value=10, step=1)
  if qty > 0:
    user_box_orders.append({"info": box, "qty": qty})

placed_boxes, unfitted_boxes = run_dbl_algorithm(
    container_info, user_box_orders, box_colors_map
)
tot_w, cg_x, cg_y, f_axle, r_axle, f_limit, r_limit, ldd_pass = calculate_ldd(
    placed_boxes, container_info
)

with tab_user:
  st.title("📦 3D Container Loading & LDD Analysis")

  container_vol = (
      container_info["Width_cm"]
      * container_info["Length_cm"]
      * container_info["Height_cm"]
  )
  used_vol = sum(
      (b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) * (b["z2"] - b["z1"])
      for b in placed_boxes
  )
  vol_utilization = (
      (used_vol / container_vol) * 100 if container_vol > 0 else 0
  )
  weight_utilization = (
      (tot_w / container_info["Max_Weight_kg"]) * 100
      if container_info["Max_Weight_kg"] > 0
      else 0
  )

  m1, m2, m3, m4 = st.columns(4)
  m1.metric("📦 Volume Util.", f"{vol_utilization:.2f} %")
  m2.metric(
      "秤️ Total Weight",
      f"{tot_w:,.1f} kg",
      f"Limit {container_info['Max_Weight_kg']:,.0f} kg"
      f" ({weight_utilization:.1f}%)",
  )
  m3.metric("🎯 CG Point (X, Y)", f"{cg_x:.0f}, {cg_y:.0f} cm")
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
                        <span style="font-size: 13px; font-weight: 600; color: #212529;">{box['Box_Name']}</span><br>
                        <small style="color: #6C757D;">{box['Customer_Name']}</small>
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

with tab_admin:
  st.title("⚙️ Master Data (Google Sheets Real-Time)")
  st.caption("Live data read directly from Google Sheets.")
  st.subheader("1. Container Master Table")
  st.dataframe(df_container, use_container_width=True)
  st.subheader("2. Box Master Table")
  st.dataframe(df_box, use_container_width=True)
