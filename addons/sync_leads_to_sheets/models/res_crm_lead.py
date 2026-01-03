import gspread
import base64
import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CRMLead(models.Model):
    _inherit = 'crm.lead'

    # Relación con el proyecto
    project_id = fields.Many2one(
        'project.project', 
        string='Proyecto para Sincronización',
        help="Selecciona el proyecto que contiene la Spreadsheet ID",
        tracking=True
    )

    # Campo técnico para evitar enviar el mismo lead dos veces
    google_sync_done = fields.Boolean(
        string='Sincronizado con Google',
        default=False,
        copy=False
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Se ejecuta cuando se crea un nuevo lead.
        Dispara la sincronización con Google Sheets.
        """
        # 1. Crear el lead normalmente
        leads = super(CRMLead, self).create(vals_list)
        
        # 2. Procesar cada lead creado
        for lead in leads:
            lead._process_new_lead()
        
        return leads

    def _process_new_lead(self):
        """Método central para procesar un lead recién creado"""
        self.ensure_one()
        
        # Solo procesar si tiene proyecto con Google Sheets habilitado
        if not self.project_id:
            _logger.info(f"Lead {self.name}: Sin proyecto asignado, no se sincroniza")
            return
            
        if not self.project_id.use_google_sheets:
            _logger.info(f"Lead {self.name}: Proyecto sin Google Sheets habilitado")
            return
            
        if self.google_sync_done:
            _logger.info(f"Lead {self.name}: Ya fue sincronizado previamente")
            return
        
        # Enviar a Google Sheets
        success, message = self._send_to_google_sheets()
        
        if success:
            self.google_sync_done = True
            _logger.info(f"✅ Lead {self.name} sincronizado con Google Sheets")
            
            # Notificar al usuario
            self._notify_sync_result(True, "Lead sincronizado con Google Sheets")
            
            # Crear tarea si es necesario
            try:
                if self.project_id.create_task_on_lead:
                    task = self._create_task_from_lead()
                    if task:
                        _logger.info(f"✅ Tarea {task.id} creada para Lead {self.name}")
                else:    
                    _logger.info(f"Creacion de tarea no asignada al proyecto {self.project_id.name}")
            except Exception as e:
                _logger.error(f"Error creando tarea: {str(e)}")
        else:
            _logger.error(f"❌ Error sincronizando Lead {self.name}: {message}")
            self._notify_sync_result(False, message)

    def _notify_sync_result(self, success, message):
        """Envía notificación al usuario sobre el resultado"""
        self.env['bus.bus']._sendone(
            self.env.user.partner_id,
            'simple_notification',
            {
                'type': 'success' if success else 'danger',
                'title': 'Google Sheets' if success else 'Error Google Sheets',
                'message': message,
                'sticky': not success,
            }
        )

    def _get_google_client(self):
        """Autenticación con Google"""
        params = self.env['ir.config_parameter'].sudo()
        key_file = params.get_param('crm_sheets.google_key_file')
        
        if not key_file:
            return False, "No se encontró el archivo JSON de credenciales"
            
        try:
            key_data = json.loads(base64.b64decode(key_file))
            return gspread.service_account_from_dict(key_data), "OK"
        except Exception as e:
            return False, str(e)

    def _send_to_google_sheets(self):
        """Envío de datos a Google Sheets"""
        if self.google_sync_done:
            return True, "Ya sincronizado"
            
        client, msg = self._get_google_client()
        if not client:
            return False, msg

        try:
            sheet_id = self.project_id.google_spreadsheet_id
            if not sheet_id:
                return False, "El proyecto no tiene Google Sheet ID"

            workbook = client.open_by_key(sheet_id)
            worksheet = workbook.get_worksheet(0)

            row = [
                fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                self.name or '',
                self.partner_id.name or self.contact_name or 'Sin nombre',
                self.email_from or '',
                self.phone or '',
                float(self.expected_revenue or 0),
                self.user_id.name or 'Sin comercial',
                self.stage_id.name or 'Sin etapa'
            ]

            worksheet.append_row(row)
            return True, "Success"

        except Exception as e:
            _logger.error(f"Error en Google Sheets: {str(e)}")
            return False, str(e)

    def _create_task_from_lead(self):
        """Crea una tarea en el proyecto seleccionado"""
        self.ensure_one()
            
        if not self.project_id:
            return False
        
        # Buscar etapa del proyecto
        stage = self.env['project.task.type'].search([
            '|',
            ('project_ids', '=', False),
            ('project_ids', 'in', [self.project_id.id])
        ], order='sequence asc', limit=1)
        
        if not stage:
            stage = self.env['project.task.type'].create({
                'name': 'Por hacer',
                'sequence': 10,
                'project_ids': [(4, self.project_id.id)]
            })
        
        # Construir descripción
        description_lines = [
            "<h3>📋 Información del Nuevo Lead:</h3>",
            "<ul>"
        ]
        
        if self.partner_id:
            description_lines.append(f"<li><strong>Cliente:</strong> {self.partner_id.name}</li>")
        elif self.contact_name:
            description_lines.append(f"<li><strong>Contacto:</strong> {self.contact_name}</li>")
        
        if self.email_from:
            description_lines.append(f"<li><strong>Email:</strong> {self.email_from}</li>")
        
        if self.phone:
            description_lines.append(f"<li><strong>Teléfono:</strong> {self.phone}</li>")
        
        if self.expected_revenue:
            description_lines.append(f"<li><strong>Valor esperado:</strong> ${self.expected_revenue:,.2f}</li>")
        
        if self.user_id:
            description_lines.append(f"<li><strong>Vendedor:</strong> {self.user_id.name}</li>")
        
        description_lines.append("</ul>")
        
        # Crear tarea
        task_vals = {
            'name': f"[LEAD-{self.id}] {self.partner_id.name or self.contact_name or self.name}",
            'project_id': self.project_id.id,
            'stage_id': stage.id,
            'description': '\n'.join(description_lines),
        }
        
        if self.partner_id:
            task_vals['partner_id'] = self.partner_id.id
        
        if self.user_id:
            task_vals['user_ids'] = [(6, 0, [self.user_id.id])]
        
        try:
            task = self.env['project.task'].create(task_vals)
            
            self.message_post(
                body=f'<p>✅ Tarea creada: <a href="#id={task.id}&model=project.task">{task.name}</a></p>',
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            return task
            
        except Exception as e:
            _logger.error(f"Error creando tarea: {str(e)}")
            return False