import hashlib
import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SocialWebhookController(http.Controller):

    @http.route(
        '/social/meta/webhook',
        type='http', auth='public', methods=['GET'], csrf=False,
    )
    def webhook_verify(self, **kwargs):
        """
        Meta llama a este endpoint para verificar que la URL es nuestra.
        Compara el hub.verify_token contra los tokens almacenados en las cuentas.
        """
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')

        if mode == 'subscribe' and challenge:
            account = request.env['social.account'].sudo().search(
                [('verify_token', '=', token), ('active', '=', True)],
                limit=1,
            )
            if account:
                _logger.info('Webhook Meta verificado para cuenta: %s', account.name)
                return challenge

        _logger.warning('Verificación de webhook fallida. Token recibido: %s', token)
        return http.Response('Forbidden', status=403)

    @http.route(
        '/social/meta/webhook',
        type='http', auth='public', methods=['POST'], csrf=False,
    )
    def webhook_receive(self, **kwargs):
        """
        Recibe eventos de Meta (Facebook Messenger e Instagram DMs).
        object == 'page'      → Facebook Messenger
        object == 'instagram' → Instagram DMs
        """
        raw_body = request.httprequest.data

        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, Exception) as e:
            _logger.error('Error parseando payload del webhook Meta: %s', e)
            return http.Response('Bad Request', status=400)

        object_type = payload.get('object')
        if object_type not in ('page', 'instagram'):
            return http.Response('OK', status=200)

        platform = 'facebook' if object_type == 'page' else 'instagram'

        for entry in payload.get('entry', []):
            page_id = str(entry.get('id', ''))

            account = request.env['social.account'].sudo().search([
                ('page_id', '=', page_id),
                ('platform', '=', platform),
                ('active', '=', True),
            ], limit=1)

            if not account:
                _logger.warning(
                    'No se encontró cuenta activa para page_id=%s plataforma=%s',
                    page_id, platform,
                )
                continue

            # Verificar firma HMAC si la cuenta tiene app_secret configurado
            if account.app_secret:
                if not self._verify_signature(raw_body, account.app_secret, request.httprequest):
                    _logger.warning('Firma inválida para cuenta %s', account.name)
                    continue

            for event in entry.get('messaging', []):
                try:
                    request.env['social.conversation'].sudo()._process_webhook_event(
                        account, event, platform,
                    )
                except Exception as e:
                    _logger.exception('Error procesando evento de %s: %s', platform, e)

        return http.Response('EVENT_RECEIVED', status=200)

    @staticmethod
    def _verify_signature(raw_body: bytes, app_secret: str, http_request) -> bool:
        """Verifica el header X-Hub-Signature-256 enviado por Meta."""
        signature_header = http_request.headers.get('X-Hub-Signature-256', '')
        if not signature_header.startswith('sha256='):
            return False
        expected = hmac.new(
            app_secret.encode('utf-8'), raw_body, hashlib.sha256,
        ).hexdigest()
        received = signature_header[len('sha256='):]
        return hmac.compare_digest(expected, received)
