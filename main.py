import os
import json
from datetime import datetime
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import pandas as pd
from fpdf import FPDF

from database import get_db, Project

# --- НАСТРОЙКИ ---
app = FastAPI(title="Программа ЭКО")
templates = Jinja2Templates(directory="templates")

# --- ЗАГРУЗКА БАЗЫ ДАННЫХ ---
df = pd.read_csv("database.csv")
df = df.fillna(0) # ВАЖНО: Заменяем пустые ячейки (NaN) на 0, иначе JSON ломается
materials_db = df.to_dict('records')

def is_arm(mat):
    name = str(mat['material_name']).lower()
    return any(word in name for word in ['арматур', 'сетка', 'проволок', 'углепластик', 'базальтопластик'])

wall_materials = [m for m in materials_db if not is_arm(m)]
arm_materials = [m for m in materials_db if is_arm(m)]

# --- ГЛАВНАЯ СТРАНИЦА ---
@app.get("/", response_class=HTMLResponse)
async def read_form(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "wall_json": json.dumps(wall_materials, ensure_ascii=False),
        "arm_json": json.dumps(arm_materials, ensure_ascii=False),
        "form_layers": "[]"
    })

# --- РАСЧЕТЫ ---
@app.post("/calculate", response_class=HTMLResponse)
async def calculate(
    request: Request, db: Session = Depends(get_db),
    mat_ids: list = Form(default=[]), 
    thicks: list = Form(default=[]),
    reinf_id: int = Form(0), reinf_mass: float = Form(0),
    gsop: float = Form(...), total_area: float = Form(...)
):
    form_layers = []
    for i in range(len(mat_ids)):
        m_id = int(mat_ids[i])
        t_str = thicks[i].strip() if thicks[i] else ""
        t = float(t_str) if t_str else 0.0
        
        layer_data = {"mat_id": m_id, "thick": t if t > 0 else ""}
        mat_obj = next((m for m in materials_db if m['id'] == m_id), None)
        
        if mat_obj:
            layer_data["mat_name"] = mat_obj['material_name']
            same_names = [m for m in wall_materials if m['material_name'] == mat_obj['material_name']]
            layer_data["dens_disabled"] = len(same_names) <= 1
            layer_data["dens_options"] = same_names
        else:
            layer_data["mat_name"] = ""
            layer_data["dens_disabled"] = True
            layer_data["dens_options"] = []
        form_layers.append(layer_data)

    calc_rows = {}
    total_mass = sum_delta = total_carbon = total_energy = 0.0
    
    for i, (mat_id_str, thick_str) in enumerate(zip(mat_ids, thicks)):
        mat_id = int(mat_id_str)
        t_str = thick_str.strip() if thick_str else ""
        thick = float(t_str) if t_str else 0.0
        
        if mat_id > 0 and thick > 0:
            mat = next((m for m in materials_db if m['id'] == mat_id), None)
            if mat:
                mass = mat['density'] * thick
                r_layer = thick / mat['thermal_conductivity'] if mat['thermal_conductivity'] > 0 else 0
                
                total_mass += mass
                sum_delta += r_layer
                total_carbon += mass * mat['carbon_factor']
                total_energy += mass * mat['embodied_energy']
                
                calc_rows[str(i)] = {
                    "name": mat['material_name'], 
                    "density": mat['density'], 
                    "thickness": thick,
                    "mass": round(mass, 2), "carbon": round(mass * mat['carbon_factor'], 2), 
                    "energy": round(mass * mat['embodied_energy'], 2), "r_layer": round(r_layer, 4)
                }

    if reinf_id > 0 and reinf_mass > 0:
        mat = next((m for m in materials_db if m['id'] == reinf_id), None)
        if mat:
            total_mass += reinf_mass
            total_carbon += reinf_mass * mat['carbon_factor']
            total_energy += reinf_mass * mat['embodied_energy']
            calc_rows["reinf"] = {
                "name": f"{mat['material_name']} ({reinf_mass} кг)",
                "density": "-", 
                "thickness": "-",
                "mass": reinf_mass, "carbon": round(reinf_mass * mat['carbon_factor'], 2), 
                "energy": round(reinf_mass * mat['embodied_energy'], 2)
            }

    R0 = 0.15841 + sum_delta
    Q1 = (0.024 * gsop) / R0
    Qt = Q1 * total_area
    V1 = Q1 / (9.3 * 0.9)
    Vt = V1 * total_area

    project_data = {
        "gsop": gsop, "total_area": total_area, "R0": round(R0, 4),
        "total_mass": round(total_mass, 2), "total_carbon": round(total_carbon, 2), "total_energy": round(total_energy, 2),
        "Q1": round(Q1, 3), "Qt": round(Qt, 3), "V1": round(V1, 3), "Vt": round(Vt, 3),
        "layers": list(calc_rows.values())
    }
    
    # Сохраняем проект без привязки к пользователю
    new_project = Project(results_json=json.dumps(project_data, ensure_ascii=False))
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    project_id = new_project.id

    response = templates.TemplateResponse("index.html", {
        "request": request,
        "wall_json": json.dumps(wall_materials, ensure_ascii=False),
        "arm_json": json.dumps(arm_materials, ensure_ascii=False),
        "form_layers": json.dumps(form_layers, ensure_ascii=False),
        "calc": calc_rows, "project_id": project_id,
        "total_mass": round(total_mass, 2), "R0": round(R0, 4),
        "total_carbon": round(total_carbon, 2), "total_energy": round(total_energy, 2),
        "Q1": round(Q1, 3), "Qt": round(Qt, 3), "V1": round(V1, 3), "Vt": round(Vt, 3),
        "gsop": gsop, "total_area": total_area,
        "reinf_id": reinf_id, "reinf_mass": reinf_mass if reinf_mass > 0 else "0",
        "reinf_name": next((m['material_name'] for m in materials_db if m['id'] == reinf_id), "")
    })
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    return response

# --- ГЕНЕРАЦИЯ PDF ---
# --- ГЕНЕРАЦИЯ PDF ---
@app.get("/download_pdf/{project_id}")
async def download_pdf(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project: raise HTTPException(status_code=404)
    
    data = json.loads(project.results_json)
    font_path = "DejaVuSans.ttf"
    if not os.path.exists(font_path): 
        raise HTTPException(status_code=500, detail="Шрифт не найден")

    pdf = FPDF()
    pdf.add_font('DejaVu', '', font_path, uni=True)
    pdf.add_page()
    pdf.set_font('DejaVu', '', 12)
    pdf.cell(0, 10, 'ПРОГРАММА ЭКО - Расчет наружной стены', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)

    # --- 1. ТАБЛИЦА СЛОЕВ ---
    col_widths = [75, 20, 15, 18, 22, 22, 18]
    headers = ['Материал', 'ρ, кг/м3', 'δ, м', 'Масса', 'СА1-А3', 'ЕА1-А3', 'δ/λ']
    pdf.set_font('DejaVu', '', 7)
    
    # Функция для таблицы слоев (автоперенос по словам и страницам)
    def draw_table_row(cells_data):
        line_h = 5
        max_lines = 1
        for i, txt in enumerate(cells_data):
            str_w = pdf.get_string_width(str(txt))
            lines = max(1, int(str_w / (col_widths[i] - 2)) + 1)
            if lines > max_lines:
                max_lines = lines
        row_h = line_h * max_lines
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        
        # Перенос на новую страницу, если строка не влезает
        if y_start + row_h > 270:
            pdf.add_page()
            y_start = pdf.get_y()
            x_start = pdf.get_x()

        # Рисуем рамки
        for i in range(len(cells_data)):
            pdf.set_xy(x_start + sum(col_widths[:i]), y_start)
            pdf.cell(col_widths[i], row_h, border=1, align='C')
        
        # Пишем текст
        for i, txt in enumerate(cells_data):
            pdf.set_xy(x_start + sum(col_widths[:i]) + 0.5, y_start + 0.5)
            align = 'L' if i == 0 else 'C'
            pdf.multi_cell(col_widths[i] - 1, line_h, str(txt), border=0, align=align)
        
        pdf.set_xy(x_start, y_start + row_h)

    # Отрисовка таблицы слоев
    draw_table_row(headers)
    for l in data["layers"]:
        draw_table_row([
            str(l.get('name', '-')), str(l.get('density', '-')), str(l.get('thickness', '-')),
            str(l.get('mass', '-')), str(l.get('carbon', '-')), str(l.get('energy', '-')), 
            str(l.get('r_layer', '-'))
        ])
    draw_table_row([
        'ИТОГО', '-', '-', str(data["total_mass"]), 
        str(data["total_carbon"]), str(data["total_energy"]), f'R0={data["R0"]}'
    ])
    
    # --- 2. ТАБЛИЦА РЕЗУЛЬТАТОВ ---
    pdf.ln(8)
    desc_w = 140  # Ширина колонки с описанием
    val_w = 50    # Ширина колонки со значением
    
    # Функция для отрисовки строк результатов
    def draw_desc_row(label, value):
        line_h = 5
        # Считаем количество строк для описания
        str_w_label = pdf.get_string_width(str(label))
        lines_label = max(1, int(str_w_label / (desc_w - 2)) + 1)
        # Считаем количество строк для значения
        str_w_val = pdf.get_string_width(str(value))
        lines_val = max(1, int(str_w_val / (val_w - 2)) + 1)
        
        # Берем максимальную высоту
        max_lines = max(lines_label, lines_val)
        row_h = line_h * max_lines
        
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        
        # Перенос на новую страницу, если не влезает
        if y_start + row_h > 270:
            pdf.add_page()
            y_start = pdf.get_y()
            x_start = pdf.get_x()
        
        # Рисуем рамки
        pdf.set_xy(x_start, y_start)
        pdf.cell(desc_w, row_h, border=1)
        pdf.set_xy(x_start + desc_w, y_start)
        pdf.cell(val_w, row_h, border=1, align='C')
        
        # Пишем описание (по левому краю)
        pdf.set_xy(x_start + 1, y_start + 1)
        pdf.multi_cell(desc_w - 2, line_h, str(label), border=0, align='L')
        
        # Пишем значение (по центру и вертикально по центру)
        val_y_offset = (row_h - (lines_val * line_h)) / 2
        pdf.set_xy(x_start + desc_w + 1, y_start + val_y_offset + 0.5)
        pdf.multi_cell(val_w - 2, line_h, str(value), border=0, align='C')
        
        # Перемещаем курсор в конец строки
        pdf.set_xy(x_start, y_start + row_h)

    # Заголовок "ИТОГО НА 1 м2:"
    pdf.set_font('DejaVu', '', 9)
    pdf.cell(190, 7, "ИТОГО НА 1 м2:", border=1, align='L')
    pdf.ln()
    pdf.set_font('DejaVu', '', 8)
    
    # Заполняем первую часть
    draw_desc_row("Масса", f"{data['total_mass']} кг")
    draw_desc_row("СА1-А3 (выбросы углерода при производстве материалов, кгСО2экв/м2)", data['total_carbon'])
    draw_desc_row("ЕА1-А3 (воплощенная энергия в материалах, МДж/м2)", data['total_energy'])
    draw_desc_row("R0 (условное сопротивление теплопередаче, м2·°С/Вт)", data['R0'])
    
    # Отступ и заголовок "3. Расчет..."
    pdf.ln(3)
    pdf.set_font('DejaVu', '', 9)
    pdf.cell(190, 7, "3. Расчет теплотехнических характеристик и расхода газа:", border=1, align='L')
    pdf.ln()
    pdf.set_font('DejaVu', '', 8)
    
    # Заполняем вторую часть
    draw_desc_row("Годовые трансмиссионные потери тепловой энергии через 1 м2 наружных стен с рассчитанным R0 усл за отопительный период (Qст.год)", f"{data['Q1']} кВт·ч/год")
    draw_desc_row("Расчет трансмиссионных потерь тепловой энергии через всю площадь стен S за отопительный период (Qгод)", f"{data['Qt']} кВт·ч/год")
    draw_desc_row("Расход природного газа (метана) на компенсацию трансмиссионных потерь тепловой энергии через 1 м2 стен в год (V1)", f"{data['V1']} м3")
    draw_desc_row("Расход природного газа (метана) на компенсацию трансмиссионных потерь тепловой энергии через всю площадь стен S в год (VОбщ)", f"{data['Vt']} м3")

    # Конвертация и возврат файла
    pdf_bytes = pdf.output()
    if isinstance(pdf_bytes, bytearray): pdf_bytes = bytes(pdf_bytes)
    elif isinstance(pdf_bytes, str): pdf_bytes = pdf_bytes.encode('latin-1')

    return Response(
        content=pdf_bytes, 
        media_type="application/pdf", 
        headers={"Content-Disposition": f"attachment; filename=eco_report_{project_id}.pdf"}
    )
app.mount("/static", StaticFiles(directory="static"), name="static")