"""Server-side translation of messages users see.

The whole system runs in one language (APP_LANGUAGE), so the backend
translates: error responses (`main.py`, chat socket) and texts stored for
later display (notification messages, document processing errors).
Keys are the English texts; a missing translation falls back to English.
Configuration errors stay English: they name .env variables for operators.
"""

from exceptions import AppError
from settings import language

_ES = {
    # Auth and sessions
    "Email or password is wrong": "El correo o la contraseña no son correctos",
    "Not authenticated": "No has iniciado sesión",
    "Insufficient permissions": "No tienes permisos suficientes",
    "Cross-origin socket": "Conexión de otro origen rechazada",
    "Too many failed sign-in attempts. Try again in {minutes} minutes.": "Demasiados intentos fallidos. Vuelve a intentarlo dentro de {minutes} minutos.",
    # Users and roles
    "User not found": "Usuario no encontrado",
    "Role not found": "Rol no encontrado",
    "A user with this email already exists": "Ya existe un usuario con este correo",
    "A role with this key already exists": "Ya existe un rol con esta clave",
    "A role with this name already exists": "Ya existe un rol con este nombre",
    "A role with this key or name already exists": "Ya existe un rol con esta clave o nombre",
    "One or more roles do not exist": "Uno o más roles no existen",
    "One or more permissions do not exist": "Uno o más permisos no existen",
    "The Admin role always has every permission": "El rol Admin siempre tiene todos los permisos",
    "The Admin role cannot be deleted": "El rol Admin no se puede eliminar",
    "The Admin role cannot be removed from the last admin": "No se puede quitar el rol Admin al último administrador",
    "You cannot delete your own account": "No puedes eliminar tu propia cuenta",
    "You cannot disable your own account": "No puedes desactivar tu propia cuenta",
    "This account is disabled": "Esta cuenta está desactivada",
    "You cannot grant permissions you do not have": "No puedes conceder permisos que no tienes",
    "You cannot change an account or role with more access than yours": "No puedes modificar una cuenta o un rol con más acceso que el tuyo",
    # Documents
    "Document not found": "Documento no encontrado",
    "This file type is not supported.": "Este tipo de archivo no es compatible.",
    "The file is empty.": "El archivo está vacío.",
    "The file is too large.": "El archivo es demasiado grande.",
    "The file content does not match its type.": "El contenido del archivo no coincide con su tipo.",
    "The file is not plain text. Save it as UTF-8 text.": "El archivo no es texto plano. Guárdalo como texto UTF-8.",
    "The file unpacks to too much data.": "El archivo se descomprime en demasiados datos.",
    "The document has no text.": "El documento no contiene texto.",
    "Could not convert the Word document.": "No se pudo convertir el documento de Word.",
    "Could not store the document.": "No se pudo guardar el documento.",
    "Could not read the document.": "No se pudo leer el documento.",
    "Could not delete the document file.": "No se pudo eliminar el archivo del documento.",
    "The document file is missing.": "Falta el archivo del documento.",
    "Could not queue the document.": "No se pudo poner el documento en cola.",
    "Could not process the document.": "No se pudo procesar el documento.",
    "Processing took too long.": "El procesamiento tardó demasiado.",
    '"{name}" is ready.': "«{name}» está listo.",
    'Could not process "{name}".': "No se pudo procesar «{name}».",
    # Search and assistant
    "Could not reach Qdrant.": "No se pudo conectar con el índice de búsqueda.",
    "Qdrant collection is not ready.": "El índice de búsqueda aún no está listo.",
    "Qdrant rejected the request.": "El índice de búsqueda rechazó la solicitud.",
    "Could not reach the chat model.": "No se pudo conectar con el modelo del asistente.",
    "The chat model is not available.": "El modelo del asistente no está disponible.",
    "The chat model failed.": "El modelo del asistente falló.",
    "The chat model returned an empty answer.": "El modelo del asistente devolvió una respuesta vacía.",
    "A reply is already in progress.": "Ya se está generando una respuesta.",
    "Your previous question is still being answered. Wait for it or stop it.": "Su pregunta anterior aún se está respondiendo. Espere o deténgala.",
    "You have asked {limit} questions in the last 10 minutes. Try again in {minutes} min.": "Ha hecho {limit} preguntas en los últimos 10 minutos. Vuelva a intentarlo en {minutes} min.",
    "Enter a message.": "Escribe un mensaje.",
    "The last message must be from the user.": "El último mensaje debe ser del usuario.",
    "Conversation not found": "Conversación no encontrada",
    "Notification not found": "Notificación no encontrada",
}

_FR = {
    # Auth and sessions
    "Email or password is wrong": "E-mail ou mot de passe incorrect",
    "Not authenticated": "Vous n’êtes pas connecté",
    "Insufficient permissions": "Autorisations insuffisantes",
    "Cross-origin socket": "Connexion d’une autre origine refusée",
    "Too many failed sign-in attempts. Try again in {minutes} minutes.": "Trop de tentatives de connexion échouées. Réessayez dans {minutes} minutes.",
    # Users and roles
    "User not found": "Utilisateur introuvable",
    "Role not found": "Rôle introuvable",
    "A user with this email already exists": "Un utilisateur avec cet e-mail existe déjà",
    "A role with this key already exists": "Un rôle avec cette clé existe déjà",
    "A role with this name already exists": "Un rôle avec ce nom existe déjà",
    "A role with this key or name already exists": "Un rôle avec cette clé ou ce nom existe déjà",
    "One or more roles do not exist": "Un ou plusieurs rôles n’existent pas",
    "One or more permissions do not exist": "Une ou plusieurs autorisations n’existent pas",
    "The Admin role always has every permission": "Le rôle Admin a toujours toutes les autorisations",
    "The Admin role cannot be deleted": "Le rôle Admin ne peut pas être supprimé",
    "The Admin role cannot be removed from the last admin": "Le rôle Admin ne peut pas être retiré au dernier administrateur",
    "You cannot delete your own account": "Vous ne pouvez pas supprimer votre propre compte",
    "You cannot disable your own account": "Vous ne pouvez pas désactiver votre propre compte",
    "This account is disabled": "Ce compte est désactivé",
    "You cannot grant permissions you do not have": "Vous ne pouvez pas accorder des autorisations que vous n’avez pas",
    "You cannot change an account or role with more access than yours": "Vous ne pouvez pas modifier un compte ou un rôle ayant plus d’accès que le vôtre",
    # Documents
    "Document not found": "Document introuvable",
    "This file type is not supported.": "Ce type de fichier n’est pas pris en charge.",
    "The file is empty.": "Le fichier est vide.",
    "The file is too large.": "Le fichier est trop volumineux.",
    "The file content does not match its type.": "Le contenu du fichier ne correspond pas à son type.",
    "The file is not plain text. Save it as UTF-8 text.": "Le fichier n’est pas du texte brut. Enregistrez-le en texte UTF-8.",
    "The file unpacks to too much data.": "Le fichier se décompresse en trop de données.",
    "The document has no text.": "Le document ne contient pas de texte.",
    "Could not convert the Word document.": "Impossible de convertir le document Word.",
    "Could not store the document.": "Impossible d’enregistrer le document.",
    "Could not read the document.": "Impossible de lire le document.",
    "Could not delete the document file.": "Impossible de supprimer le fichier du document.",
    "The document file is missing.": "Le fichier du document est introuvable.",
    "Could not queue the document.": "Impossible de mettre le document en file d’attente.",
    "Could not process the document.": "Impossible de traiter le document.",
    "Processing took too long.": "Le traitement a pris trop de temps.",
    '"{name}" is ready.': "« {name} » est prêt.",
    'Could not process "{name}".': "Impossible de traiter « {name} ».",
    # Search and assistant
    "Could not reach Qdrant.": "Impossible de joindre l’index de recherche.",
    "Qdrant collection is not ready.": "L’index de recherche n’est pas encore prêt.",
    "Qdrant rejected the request.": "L’index de recherche a refusé la requête.",
    "Could not reach the chat model.": "Impossible de joindre le modèle de l’assistant.",
    "The chat model is not available.": "Le modèle de l’assistant n’est pas disponible.",
    "The chat model failed.": "Le modèle de l’assistant a échoué.",
    "The chat model returned an empty answer.": "Le modèle de l’assistant a renvoyé une réponse vide.",
    "A reply is already in progress.": "Une réponse est déjà en cours.",
    "Your previous question is still being answered. Wait for it or stop it.": "La réponse à votre question précédente est encore en cours. Attendez-la ou arrêtez-la.",
    "You have asked {limit} questions in the last 10 minutes. Try again in {minutes} min.": "Vous avez posé {limit} questions ces 10 dernières minutes. Réessayez dans {minutes} min.",
    "Enter a message.": "Saisissez un message.",
    "The last message must be from the user.": "Le dernier message doit venir de l’utilisateur.",
    "Conversation not found": "Conversation introuvable",
    "Notification not found": "Notification introuvable",
}

CATALOG: dict[str, dict[str, str]] = {"es": _ES, "fr": _FR}


def t(message: str, **params: object) -> str:
    """`message` in the system language. Params fill {placeholders} after
    translation. Unknown messages (and English) pass through unchanged."""
    try:
        table = CATALOG.get(language(), {})
    except AppError:
        table = {}
    template = table.get(message, message)
    return template.format(**params) if params else template
