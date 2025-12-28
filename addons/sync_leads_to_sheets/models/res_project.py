# -*- coding: utf-8 -*-
from odoo import models, fields

class Project(models.Model):
    _inherit = 'project.project'

    # 1. El interruptor: Nos dice si este proyecto en específico debe sincronizar
    use_google_sheets = fields.Boolean(
        string="Sincronizar con Google Sheets",
        default=False,
        help="Si está activo, los leads de este proyecto se enviarán a la hoja de cálculo."
    )

    # 2. El destino: Aquí guardaremos el ID largo de la URL de Google Sheets
    google_spreadsheet_id = fields.Char(
        string="ID de Google Spreadsheet",
        help="El ID único de la hoja de cálculo (se encuentra en la URL)."
    )