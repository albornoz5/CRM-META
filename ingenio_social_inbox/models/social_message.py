from odoo import models, fields


class SocialMessage(models.Model):
    _name = 'social.message'
    _description = 'Mensaje de Red Social'
    _order = 'timestamp asc, id asc'

    conversation_id = fields.Many2one(
        'social.conversation', required=True, ondelete='cascade', index=True,
    )
    direction = fields.Selection([
        ('inbound', 'Entrante'),
        ('outbound', 'Saliente'),
    ], required=True)
    message_id = fields.Char('ID Mensaje Meta', index=True)
    body = fields.Text('Mensaje', required=True)
    timestamp = fields.Datetime('Fecha/Hora', required=True)
    author_name = fields.Char('Autor')
    attachment_url = fields.Char('URL Adjunto')

    _sql_constraints = [
        ('unique_message_id', 'UNIQUE(message_id)',
         'Este mensaje ya fue procesado anteriormente.'),
    ]
