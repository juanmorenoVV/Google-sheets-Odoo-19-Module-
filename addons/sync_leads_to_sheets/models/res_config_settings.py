from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # campos de configuracion del google  

    # Campo para subir el archivo JSON
    google_drive_key_file = fields.Binary(
        string="Archivo JSON de Google",
        help="Sube aquí el archivo JSON de tu Service Account de Google Cloud"
    )

    # Campo técnico para guardar el nombre del archivo
    google_drive_key_filename = fields.Char(string="Nombre del Archivo JSON")

    # Campo para seleccionar qué proyectos se van a sincronizar
    google_sheets_project_ids = fields.Many2many(
        'project.project',
        string="Proyectos Seleccionados",
        help="Los proyectos que elijas aquí aparecerán abajo para asignarles su ID de Google Sheet"
    )


    def set_values(self):
        super(ResConfigSettings, self).set_values()
        # Guardamos el JSON en los parámetros del sistema
        self.env['ir.config_parameter'].sudo().set_param(
            'crm_sheets.google_key_file', self.google_drive_key_file or False
        )

        # LÓGICA AUTOMÁTICA:
        # Si un proyecto está en esta lista, le ponemos use_google_sheets = True
        # Si lo quitaron de la lista, le ponemos False.
        all_projects = self.env['project.project'].search([])
        for project in all_projects:
            if project in self.google_sheets_project_ids:
                project.use_google_sheets = True
            else:
                project.use_google_sheets = False

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        # Al abrir la pantalla, cargamos todos los proyectos que el usuario ya activó
        active_projects = self.env['project.project'].search([('use_google_sheets', '=', True)])
        
        res.update(
            google_drive_key_file=self.env['ir.config_parameter'].sudo().get_param('crm_sheets.google_key_file'),
            google_sheets_project_ids=[(6, 0, active_projects.ids)],
        )
        return res