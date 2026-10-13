# ruff: noqa: E501  (a catalog of user-facing sentences: wrapping them would only hurt reading them)
"""Texts of the emails, in the two languages of the product.

Like the spoken texts (``agilina_shared.i18n``), nothing user-facing is written inside
the templates: they only place these strings. A test fails if a template exists in one
language and not in the other. Values may use ``{{ parameter }}``, resolved at render time.
"""

from agilina_shared.enums import Language

LAYOUT: dict[Language, dict[str, str]] = {
    Language.ES: {
        "tagline": "Tu Scrum Master virtual para la reunión diaria",
        "footer": "Este es un mensaje automático de Agilina. No respondas a este correo.",
    },
    Language.EN: {
        "tagline": "Your virtual Scrum Master for the Daily Stand-up",
        "footer": "This is an automatic message from Agilina. Please do not reply to it.",
    },
}

TEMPLATES: dict[str, dict[Language, dict[str, str]]] = {
    "test": {
        Language.ES: {
            "subject": "Agilina: prueba de correo",
            "preheader": "Si ves este mensaje, el envío de correo de Agilina funciona.",
            "title": "El correo funciona",
            "intro": (
                "Este es un mensaje de prueba. Si lo ves con su diseño, el envío de "
                "correo de Agilina está bien configurado."
            ),
            "details": "Con qué se envió",
            "server": "Servidor",
            "security": "Seguridad",
            "security_none": "Sin cifrar (solo para pruebas)",
            "security_starttls": "Cifrado con STARTTLS",
            "security_tls": "Cifrado con TLS",
            "sender": "Remitente",
        },
        Language.EN: {
            "subject": "Agilina: email test",
            "preheader": "If you can see this message, Agilina's email delivery works.",
            "title": "Email delivery works",
            "intro": (
                "This is a test message. If you can see it with its design, Agilina's "
                "email delivery is configured correctly."
            ),
            "details": "How it was sent",
            "server": "Server",
            "security": "Security",
            "security_none": "Unencrypted (testing only)",
            "security_starttls": "Encrypted with STARTTLS",
            "security_tls": "Encrypted with TLS",
            "sender": "Sender",
        },
    },
    "invitation": {
        Language.ES: {
            "subject": "Te invitaron a {{ team_name }} en Agilina",
            "preheader": "Activa tu cuenta para entrar al equipo {{ team_name }}.",
            "title": "Te invitaron a {{ team_name }}",
            "greeting": "Hola {{ name }},",
            "intro": "Te invitaron a unirte al equipo {{ team_name }} en Agilina, el Scrum Master virtual de la reunión diaria.",
            "intro_by": "{{ inviter_name }} te invitó a unirte al equipo {{ team_name }} en Agilina, el Scrum Master virtual de la reunión diaria.",
            "cta": "Activar mi cuenta",
            "steps": "Elige una contraseña y entrarás directo a tu equipo.",
            "expiry": "El enlace vence el {{ expires_on }} y solo puede usarse una vez.",
            "fallback": "Si el botón no funciona, copia y pega este enlace en tu navegador:",
            "ignore": "Si no esperabas esta invitación, ignora este mensaje: sin activar el enlace no pasa nada.",
        },
        Language.EN: {
            "subject": "You were invited to {{ team_name }} on Agilina",
            "preheader": "Activate your account to join the {{ team_name }} team.",
            "title": "You were invited to {{ team_name }}",
            "greeting": "Hi {{ name }},",
            "intro": "You were invited to join the {{ team_name }} team on Agilina, the virtual Scrum Master of your daily.",
            "intro_by": "{{ inviter_name }} invited you to join the {{ team_name }} team on Agilina, the virtual Scrum Master of your daily.",
            "cta": "Activate my account",
            "steps": "Choose a password and you will go straight to your team.",
            "expiry": "The link expires on {{ expires_on }} and can only be used once.",
            "fallback": "If the button does not work, copy and paste this link into your browser:",
            "ignore": "If you were not expecting this invitation, ignore this message: nothing happens unless the link is activated.",
        },
    },
    "member_added": {
        Language.ES: {
            "subject": "Ahora formas parte de {{ team_name }} en Agilina",
            "preheader": "Ya puedes entrar al equipo {{ team_name }} con tu cuenta de siempre.",
            "title": "Ahora formas parte de {{ team_name }}",
            "greeting": "Hola {{ name }},",
            "intro": "Te agregaron al equipo {{ team_name }} en Agilina, el Scrum Master virtual de la reunión diaria.",
            "intro_by": "{{ inviter_name }} te agregó al equipo {{ team_name }} en Agilina, el Scrum Master virtual de la reunión diaria.",
            "no_activation": "Como ya tienes una cuenta, no hace falta activar nada: entra con tu correo y tu contraseña de siempre.",
            "cta": "Abrir el equipo",
            "fallback": "Si el botón no funciona, copia y pega este enlace en tu navegador:",
            "unexpected": "Si no esperabas este mensaje, habla con quien administra el equipo.",
        },
        Language.EN: {
            "subject": "You are now part of {{ team_name }} on Agilina",
            "preheader": "You can now open the {{ team_name }} team with your usual account.",
            "title": "You are now part of {{ team_name }}",
            "greeting": "Hi {{ name }},",
            "intro": "You were added to the {{ team_name }} team on Agilina, the virtual Scrum Master of your daily.",
            "intro_by": "{{ inviter_name }} added you to the {{ team_name }} team on Agilina, the virtual Scrum Master of your daily.",
            "no_activation": "Since you already have an account, there is nothing to activate: sign in with your usual email and password.",
            "cta": "Open the team",
            "fallback": "If the button does not work, copy and paste this link into your browser:",
            "unexpected": "If you were not expecting this message, talk to whoever manages the team.",
        },
    },
    "new_invitation_request": {
        Language.ES: {
            "subject": "{{ requester_name }} necesita una invitación nueva a {{ team_name }}",
            "preheader": "Su enlace de invitación ya no sirve.",
            "title": "{{ requester_name }} necesita una invitación nueva",
            "greeting": "Hola {{ admin_name }},",
            "intro": "{{ requester_name }} ({{ requester_email }}) intentó activar su cuenta del equipo {{ team_name }} y pidió una invitación nueva.",
            "reason_expired": "Su enlace venció: las invitaciones duran 7 días.",
            "reason_accepted": "Su enlace ya se había usado: puede que ya tenga una cuenta.",
            "reason_revoked": "Su invitación fue cancelada.",
            "action": "Si quieres que entre al equipo, invítalo de nuevo desde la configuración del equipo.",
        },
        Language.EN: {
            "subject": "{{ requester_name }} needs a new invitation to {{ team_name }}",
            "preheader": "Their invitation link no longer works.",
            "title": "{{ requester_name }} needs a new invitation",
            "greeting": "Hi {{ admin_name }},",
            "intro": "{{ requester_name }} ({{ requester_email }}) tried to activate their account in the {{ team_name }} team and asked for a new invitation.",
            "reason_expired": "Their link expired: invitations last 7 days.",
            "reason_accepted": "Their link had already been used: they may already have an account.",
            "reason_revoked": "Their invitation was cancelled.",
            "action": "If you want them in the team, invite them again from the team settings.",
        },
    },
}
