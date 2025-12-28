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



    def _process_won_lead(self):
        """ Método central para procesar un lead ganado """
        self.ensure_one()
        
        notifications = []
        
        # 1. Enviar a Google Sheets si aplica
        if self.project_id and self.project_id.use_google_sheets and not self.google_sync_done:
            success, message = self._send_to_google_sheets()
            
            if success:
                self.google_sync_done = True
                notifications.append("✅ Sincronizado con Google Sheets")
                
                # 2. Crear tarea SOLO si Google fue exitoso
                try:
                    task = self._create_task_from_lead()
                    if task:
                        notifications.append(f"✅ Tarea creada: {task.name}")
                        _logger.info(f"Tarea {task.id} creada para Lead {self.name}")
                except Exception as e:
                    _logger.error(f"Error creando tarea: {str(e)}")
                    notifications.append("⚠️ No se pudo crear la tarea")
            else:
                notifications.append(f"❌ Error Google: {message}")
        
        return notifications


    def action_set_won(self):
        """ Cuando usan el botón """
        res = super(CRMLead, self).action_set_won()
        
        for lead in self:
            notifications = lead._process_won_lead()
            
            if notifications:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Lead Ganado',
                        'message': ' | '.join(notifications),
                        'type': 'success' if '❌' not in ' '.join(notifications) else 'warning',
                        'sticky': False,
                    }
                }
        
        return res

    def write(self, vals):
        """ Cuando arrastran """
        old_stages = {lead.id: lead.stage_id.id for lead in self}
        
        res = super(CRMLead, self).write(vals)
        
        if 'stage_id' in vals:
            for lead in self.filtered(lambda l: l.stage_id.is_won):
                old_stage = old_stages.get(lead.id)
                
                # Si acaba de pasar a Won
                if old_stage != lead.stage_id.id:
                    notifications = lead._process_won_lead()
                    
                    # Log para debug
                    if notifications:
                        _logger.info(f"Lead {lead.name} procesado: {notifications}")
        
        return res

    @api.model
    def _notify_success_drag(self):
        """ Notificación de éxito para drag & drop """
        # Usar el sistema de notificaciones del cliente web
        self.env['bus.bus']._sendone(
            self.env.user.partner_id,
            'notification',
            {
                'type': 'success',
                'title': 'Google Sheets',
                'message': 'Lead sincronizado correctamente',
                'sticky': False,
            }
        )
        
    @api.model  
    def _notify_error_drag(self, error_msg):
        """ Notificación de error para drag & drop """
        self.env['bus.bus']._sendone(
            self.env.user.partner_id,
            'notification',
            {
                'type': 'danger',
                'title': 'Error Google Sheets',
                'message': f'No se pudo sincronizar: {error_msg}',
                'sticky': True,
            }
        )

    def _get_google_client(self):
        """ Autenticación """
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
        """ Envío de datos con retorno de estado """
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
            _logger.info(f"Lead {self.name} enviado a Google Sheets")

            return True, "Success"

        except Exception as e:
            _logger.error(f"Error en Google Sheets: {str(e)}")
            return False, str(e)

    def _create_task_from_lead(self):
        """ Crea una tarea en el proyecto seleccionado con la info del Lead """
        self.ensure_one()
            
        if not self.project_id:
            _logger.error(f"No hay proyecto asignado al Lead {self.name}")
            return False
        
        # 1. Buscar etapas del proyecto (pueden ser específicas o globales)
        # Primero intentamos etapas específicas del proyecto
        stage = self.env['project.task.type'].search([
            '|',
            ('project_ids', '=', False),  # Etapas globales (para todos los proyectos)
            ('project_ids', 'in', [self.project_id.id])  # Etapas específicas de este proyecto
        ], order='sequence asc', limit=1)
        
        # Si no hay ninguna etapa, creamos una por defecto
        if not stage:
            stage = self.env['project.task.type'].create({
                'name': 'Por hacer',
                'sequence': 10,
                'project_ids': [(4, self.project_id.id)]
            })
            _logger.warning(f"Se creó etapa por defecto para proyecto {self.project_id.name}")
        
        _logger.info(f"Creando tarea en etapa: {stage.name}")
        
        # 2. Construir descripción HTML mejorada
        description_lines = []
        description_lines.append("<h3>📋 Información del Lead Ganado:</h3>")
        description_lines.append("<ul>")
        
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
        
        # 3. Valores de la tarea con stage_id incluido
        task_vals = {
            'name': f"[LEAD-{self.id}] {self.partner_id.name or self.contact_name or self.name}",
            'project_id': self.project_id.id,
            'stage_id': stage.id,  # 🔥 ESTO ES LO IMPORTANTE
            'description': '\n'.join(description_lines),
        }
        
        # Solo agregar partner si existe
        if self.partner_id:
            task_vals['partner_id'] = self.partner_id.id
        
        # Asignar al mismo usuario del lead si existe
        if self.user_id:
            task_vals['user_ids'] = [(6, 0, [self.user_id.id])]
        
        # 4. Crear la tarea
        try:
            task = self.env['project.task'].create(task_vals)
            _logger.info(f"✅ Tarea creada: {task.name} en etapa {stage.name}")
            
            # 5. Agregar referencia cruzada en el Lead
            self.message_post(
                body=f'<p>✅ Tarea creada en proyecto <strong>{self.project_id.name}</strong>:</p>'
                    f'<p><a href="#id={task.id}&model=project.task&view_type=form">{task.name}</a></p>',
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            # 6. Opcional: Agregar referencia en la tarea sobre el Lead
            task.message_post(
                body=f'<p>📥 Tarea generada desde Lead ganado:</p>'
                    f'<p><a href="#id={self.id}&model=crm.lead&view_type=form">{self.name}</a></p>',
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            return task
            
        except Exception as e:
            _logger.error(f"❌ Error creando tarea: {str(e)}")
            self.message_post(
                body=f'<p>⚠️ Error al crear tarea: {str(e)}</p>',
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            return False