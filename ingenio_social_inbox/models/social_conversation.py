import logging
import requests
from datetime import datetime, timezone

from markupsafe import Markup, escape
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PLATFORM_ICONS = {
    'facebook': '📘',
    'instagram': '📸',
}


class SocialConversation(models.Model):
    _name = 'social.conversation'
    _description = 'Conversación de Red Social'
    _order = 'last_message_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(compute='_compute_name', store=True)
    platform = fields.Selection([
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
    ], string='Plataforma', required=True)
    account_id = fields.Many2one(
        'social.account', string='Cuenta', required=True, ondelete='cascade', index=True,
    )
    sender_id = fields.Char('ID Remitente', required=True, index=True)
    sender_name = fields.Char('Nombre Remitente')
    state = fields.Selection([
        ('new', 'Nuevo'),
        ('open', 'Abierto'),
        ('converted', 'Convertido'),
        ('closed', 'Cerrado'),
    ], default='new', string='Estado', tracking=True)
    lead_id = fields.Many2one('crm.lead', string='Lead', copy=False)
    partner_id = fields.Many2one('res.partner', string='Contacto')
    user_id = fields.Many2one(
        'res.users', string='Vendedor', default=lambda self: self.env.user,
    )
    last_message = fields.Text('Último Mensaje')
    last_message_date = fields.Datetime('Fecha Último Mensaje')
    unread = fields.Boolean('Sin Leer', default=True)
    social_message_ids = fields.One2many('social.message', 'conversation_id', string='Mensajes')
    social_message_count = fields.Integer(compute='_compute_message_count', string='Mensajes')

    # Campo de respuesta del vendedor
    reply_text = fields.Text('Respuesta')

    # HTML renderizado del chat
    messages_html = fields.Html(
        compute='_compute_messages_html', sanitize=False, string='Chat',
    )

    _sql_constraints = [
        ('unique_sender_account', 'UNIQUE(sender_id, account_id)',
         'Ya existe una conversación con este remitente en esta cuenta.'),
    ]

    @api.depends('sender_name', 'platform', 'sender_id')
    def _compute_name(self):
        for rec in self:
            platform_label = dict(rec._fields['platform'].selection or []).get(rec.platform, '')
            rec.name = f"{rec.sender_name or rec.sender_id} · {platform_label}"

    @api.depends('social_message_ids')
    def _compute_message_count(self):
        for rec in self:
            rec.social_message_count = len(rec.social_message_ids)

    @api.depends(
        'social_message_ids', 'social_message_ids.body', 'social_message_ids.direction',
        'social_message_ids.timestamp', 'social_message_ids.author_name', 'sender_name',
    )
    def _compute_messages_html(self):
        for rec in self:
            parts = []
            for msg in rec.social_message_ids.sorted('timestamp'):
                is_out = msg.direction == 'outbound'
                wrapper_cls = 'si-msg-out' if is_out else 'si-msg-in'
                author = escape(
                    msg.author_name or ('Vendedor' if is_out else (rec.sender_name or rec.sender_id))
                )
                time_str = msg.timestamp.strftime('%d/%m %H:%M') if msg.timestamp else ''
                body = escape(msg.body or '')
                parts.append(Markup(
                    f'<div class="si-msg-wrapper {wrapper_cls}">'
                    f'<div class="si-msg-bubble">'
                    f'<div class="si-msg-body">{body}</div>'
                    f'<div class="si-msg-meta">{author} · {time_str}</div>'
                    f'</div></div>'
                ))
            rec.messages_html = (
                Markup('').join(parts)
                if parts
                else Markup('<p class="si-empty">Sin mensajes todavía.</p>')
            )

    # ── Acciones de estado ────────────────────────────────────────────────────

    def action_mark_read(self):
        self.write({'unread': False})

    def action_close(self):
        self.write({'state': 'closed', 'unread': False})

    def action_reopen(self):
        self.write({'state': 'open'})

    # ── Enviar respuesta ──────────────────────────────────────────────────────

    def action_send_reply(self):
        self.ensure_one()
        text = (self.reply_text or '').strip()
        if not text:
            raise UserError(_('Escribí un mensaje antes de enviar.'))

        account = self.account_id
        if not account.access_token:
            raise UserError(_('La cuenta no tiene un Token de Acceso configurado.'))

        self._send_to_meta(account, text)

        self.env['social.message'].create({
            'conversation_id': self.id,
            'direction': 'outbound',
            'body': text,
            'timestamp': fields.Datetime.now(),
            'author_name': self.env.user.name,
        })
        self.write({
            'last_message': text,
            'last_message_date': fields.Datetime.now(),
            'reply_text': False,
            'unread': False,
            'state': 'open' if self.state == 'new' else self.state,
        })

    def _send_to_meta(self, account, text):
        if self.platform == 'instagram':
            send_page_id = account.facebook_page_id or account.page_id
        else:
            send_page_id = account.page_id

        url = f'https://graph.facebook.com/v19.0/{send_page_id}/messages'
        payload = {
            'recipient': {'id': self.sender_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE',
        }
        try:
            resp = requests.post(
                url,
                params={'access_token': account.access_token},
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.error('Error Meta API al enviar a %s: %s', self.sender_id, e)
            raise UserError(_(f'Error al enviar el mensaje a Meta: {e}'))

    # ── Crear Lead ────────────────────────────────────────────────────────────

    def action_create_lead(self):
        self.ensure_one()
        if self.lead_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'crm.lead',
                'res_id': self.lead_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

        transcript_lines = []
        for msg in self.social_message_ids.sorted('timestamp'):
            author = msg.author_name or ('Vendedor' if msg.direction == 'outbound' else self.sender_name)
            time_str = msg.timestamp.strftime('%d/%m/%Y %H:%M') if msg.timestamp else ''
            transcript_lines.append(f'[{time_str}] {author}: {msg.body}')
        description = '\n'.join(transcript_lines)

        platform_name = 'Facebook' if self.platform == 'facebook' else 'Instagram'
        lead_name = f'{platform_name} — {self.sender_name or self.sender_id}'

        source = self.env['utm.source'].search([('name', 'ilike', platform_name)], limit=1)
        if not source:
            source = self.env['utm.source'].create({'name': platform_name})

        lead = self.env['crm.lead'].create({
            'name': lead_name,
            'description': description,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'user_id': self.user_id.id,
            'source_id': source.id,
            'type': 'lead',
        })
        self.write({'lead_id': lead.id, 'state': 'converted'})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Lead creado'),
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── Procesamiento de webhook ──────────────────────────────────────────────

    @api.model
    def _process_webhook_event(self, account, event, platform):
        sender_id = event.get('sender', {}).get('id')
        if not sender_id or sender_id == account.page_id:
            return

        message_data = event.get('message', {})
        if not message_data or message_data.get('is_echo'):
            return

        message_mid = message_data.get('mid')
        text = message_data.get('text', '')
        attachments = message_data.get('attachments', [])

        if not text and not attachments:
            return

        # Evitar duplicados
        if message_mid and self.env['social.message'].sudo().search(
            [('message_id', '=', message_mid)], limit=1
        ):
            return

        raw_ts = event.get('timestamp', 0)
        msg_dt = (
            datetime.fromtimestamp(raw_ts / 1000, tz=timezone.utc).replace(tzinfo=None)
            if raw_ts else fields.Datetime.now()
        )

        conversation = self.search([
            ('sender_id', '=', sender_id),
            ('account_id', '=', account.id),
        ], limit=1)

        if not conversation:
            sender_name = self._fetch_sender_name(account, sender_id, platform)
            conversation = self.create({
                'platform': platform,
                'account_id': account.id,
                'sender_id': sender_id,
                'sender_name': sender_name or sender_id,
                'state': 'new',
            })

        body = text or (f'[Adjunto: {attachments[0].get("type", "archivo")}]' if attachments else '[Mensaje]')

        self.env['social.message'].create({
            'conversation_id': conversation.id,
            'direction': 'inbound',
            'message_id': message_mid,
            'body': body,
            'timestamp': msg_dt,
            'author_name': conversation.sender_name,
        })

        conversation.write({
            'last_message': body[:200],
            'last_message_date': msg_dt,
            'unread': True,
            'state': 'open' if conversation.state in ('new',) else conversation.state,
        })

    @api.model
    def _fetch_sender_name(self, account, sender_id, platform):
        try:
            fields_param = 'name,username' if platform == 'instagram' else 'name,first_name,last_name'
            resp = requests.get(
                f'https://graph.facebook.com/v19.0/{sender_id}',
                params={'fields': fields_param, 'access_token': account.access_token},
                timeout=5,
            )
            if resp.ok:
                data = resp.json()
                return data.get('name') or data.get('username')
        except Exception as e:
            _logger.warning('No se pudo obtener el nombre del remitente %s: %s', sender_id, e)
        return None
