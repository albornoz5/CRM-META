{
    'name': 'Ingenio Social Inbox',
    'version': '19.0.1.0.0',
    'summary': 'Inbox unificado para mensajes de Facebook e Instagram',
    'description': """
        Recibe y gestiona conversaciones de Facebook Messenger e Instagram DMs
        directamente en Odoo. Los vendedores pueden ver, responder y convertir
        conversaciones en leads del CRM con un solo botón.
    """,
    'category': 'Social',
    'author': 'Ingenio',
    'depends': ['mail', 'crm', 'utm', 'base'],
    'data': [
        'security/ir.model.access.csv',
        'views/social_account_views.xml',
        'views/social_conversation_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ingenio_social_inbox/static/src/css/social_inbox.css',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'OPL-1',
}
