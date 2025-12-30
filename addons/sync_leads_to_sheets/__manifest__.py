# -*- coding: utf-8 -*-
{
    'name': 'Sync Leads To Sheets',
    'version': '1.0',
    'summary': 'Automatización de Leads ganados a Tareas de Proyecto y Google Sheets',
    'category': 'Sales/CRM',
    'author': 'Tu Nombre',
    'depends': [
        'crm', 
        'project', 
        'base_setup'  # Necesario para heredar los ajustes generales
    ],
    'data': [
        # 'security/ir.model.access.csv',
<<<<<<< Updated upstream
=======
        # 'wizard/lead_to_task_wizard_view.xml',
>>>>>>> Stashed changes
        'views/res_config_settings.xml',
        # 'views/project_views.xml',
        'views/res_crm_lead.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}