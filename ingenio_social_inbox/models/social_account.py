from odoo import models, fields, api


class SocialAccount(models.Model):
    _name = 'social.account'
    _description = 'Cuenta de Red Social Meta'

    name = fields.Char('Nombre', required=True)
    platform = fields.Selection([
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
    ], string='Plataforma', required=True)
    page_id = fields.Char(
        'ID de Página/Cuenta', required=True,
        help='El ID numérico de la Página de Facebook o cuenta de Instagram Business.',
    )
    facebook_page_id = fields.Char(
        'Facebook Page ID (solo Instagram)',
        help='Solo para Instagram: ID numérico de la Página de Facebook vinculada (ej: 269148316453787). Requerido para enviar respuestas.',
    )
    access_token = fields.Char(
        'Page Access Token', required=True,
        help='Facebook Page Access Token. Para Instagram usar el token de la Página de Facebook vinculada.',
    )
    verify_token = fields.Char(
        'Verify Token', required=True,
        help='Token de verificación que vas a configurar en el webhook de Meta. Puede ser cualquier texto secreto.',
    )
    app_secret = fields.Char(
        'App Secret',
        help='App Secret de tu Meta App. Opcional, se usa para verificar la firma de los webhooks.',
    )
    active = fields.Boolean('Activo', default=True)
    conversation_ids = fields.One2many('social.conversation', 'account_id', string='Conversaciones')
    conversation_count = fields.Integer(compute='_compute_counts', string='Conversaciones')
    unread_count = fields.Integer(compute='_compute_counts', string='Sin leer')

    @api.depends('conversation_ids', 'conversation_ids.unread')
    def _compute_counts(self):
        for rec in self:
            rec.conversation_count = len(rec.conversation_ids)
            rec.unread_count = len(rec.conversation_ids.filtered('unread'))

    def action_open_conversations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Conversaciones — {self.name}',
            'res_model': 'social.conversation',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id},
        }
