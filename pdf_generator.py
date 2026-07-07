from fpdf import FPDF
import os

class EcoPDF(FPDF):
    def header(self):
        self.set_font('DejaVu', '', 12)
        self.cell(0, 8, 'ПРОГРАММА ЭКО - Расчет наружной стены', border=0, align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font('DejaVu', '', 8)
        self.cell(0, 10, f'Страница {self.page_no()}', align='C')

def build_pdf(project_name, layers, gsop, total_area, total_mass, R0, total_carbon, total_energy, Q_wall_1m2, Q_total, V1, V_total):
    pdf = EcoPDF()
    
    # Добавляем шрифт с кириллицей (файл DejaVuSans.ttf должен лежать рядом)
    font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
    pdf.add_font('DejaVu', '', font_path, uni=True)
    
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font('DejaVu', '', 10)
    pdf.cell(0, 7, f'Проект: {project_name}', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Таблица 1
    pdf.set_font('DejaVu', '', 7)
    col_widths = [65, 20, 20, 25, 30, 30]
    headers = ['Материал', 'ρ, кг/м3', 'δ, м', 'Масса, кг', 'СА1-А3, кг', 'ЕА1-А3, МДж']
    
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, border=1, align='C')
    pdf.ln()
    
    for l in layers:
        pdf.cell(col_widths[0], 6, str(l['name'])[:35], border=1)
        pdf.cell(col_widths[1], 6, str(l['density']), border=1, align='C')
        pdf.cell(col_widths[2], 6, str(l['thickness']), border=1, align='C')
        pdf.cell(col_widths[3], 6, str(l['mass']), border=1, align='C')
        pdf.cell(col_widths[4], 6, str(l['carbon']), border=1, align='C')
        pdf.cell(col_widths[5], 6, str(l['energy']), border=1, align='C')
        pdf.ln()
        
    pdf.set_font('DejaVu', '', 7)
    pdf.cell(sum(col_widths[:3]), 6, 'ИТОГО', border=1, align='C')
    pdf.cell(col_widths[3], 6, str(total_mass), border=1, align='C')
    pdf.cell(col_widths[4], 6, str(total_carbon), border=1, align='C')
    pdf.cell(col_widths[5], 6, str(total_energy), border=1, align='C')
    pdf.ln(10)

    # Таблица 2
    pdf.set_font('DejaVu', '', 9)
    results = [
        ('ГСОП региона', gsop),
        ('Площадь стен S, м2', total_area),
        ('Условное сопротивление R0, м2·°С/Вт', R0),
        ('Потери 1 м2 (Qст.год), кВт·ч/год', Q_wall_1m2),
        ('Потери всего (Qгод), кВт·ч/год', Q_total),
        ('Расход газа на 1 м2 (V1), м3', V1),
        ('Расход газа всего (VОбщ), м3', V_total),
    ]
    
    for label, val in results:
        pdf.cell(120, 7, label, border=1)
        pdf.cell(70, 7, str(val), border=1, align='C')
        pdf.ln()

    return pdf.output()