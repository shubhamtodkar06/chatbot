# chatbot_project/middleware.py
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from urllib.parse import parse_qs

# Import necessary parts from Simple JWT
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

User = get_user_model()

class JwtAuthMiddleware:
    """
    Custom middleware that authenticates users using JWT from the WebSocket URL query string.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # --- Add Print Statements for Debugging ---
        print("Middleware: Starting WebSocket authentication process.")

        query_string = scope.get('query_string', b'').decode('utf-8')
        print(f"Middleware: Raw query string: {query_string}") # See the full query string
        query_params = parse_qs(query_string)
        print(f"Middleware: Parsed query params: {query_params}") # See parsed parameters
        token_list = query_params.get('token') # parse_qs returns a list

        token = token_list[0] if token_list else None # Safely get the token value
        print(f"Middleware: Extracted token: {token}") # See if token was found

        scope['user'] = AnonymousUser() # Set default AnonymousUser

        # If a token is found, attempt to authenticate
        if token:
            print("Middleware: Token found, attempting to validate.")
            try:
                # Validate the token using simplejwt's AccessToken
                access_token = AccessToken(token)
                print(f"Middleware: Token validated successfully. Payload: {access_token.payload}") # See token payload

                user_id = access_token['user_id'] # Extract user_id
                print(f"Middleware: Extracted user ID: {user_id}")

                # Get the user object from the database asynchronously
                # Use database_sync_to_async because ORM calls are synchronous
                user = await database_sync_to_async(User.objects.get)(id=user_id)
                scope['user'] = user # Assign the authenticated user

                print(f"Middleware: Successfully authenticated user: {scope['user'].username}")

            except (InvalidToken, TokenError) as e:
                print(f"Middleware: JWT validation failed: {e}")
                # Authentication failed, scope['user'] remains AnonymousUser

            except User.DoesNotExist:
                 print(f"Middleware: User with ID {user_id} not found in database.")
                 # Authentication failed, scope['user'] remains AnonymousUser

            except Exception as e:
                 # Catch any other unexpected errors during authentication
                 print(f"Middleware: Unexpected error during authentication: {e}")
                 # scope['user'] remains AnonymousUser

        else:
            # No token provided, user remains anonymous (set above)
            print("Middleware: No token provided.")

        # Call the next ASGI application (likely the URLRouter and consumer)
        print(f"Middleware: Passing connection to next layer. User is {scope['user'].username if scope['user'] and not scope['user'].is_anonymous else 'Anonymous'}")
        return await self.inner(scope, receive, send)


def JwtAuthMiddlewareStack(inner):
    # You can wrap in other middleware here if needed
    # DatabaseSyncToAsync is often put here, but our middleware handles DB calls internally.
    return JwtAuthMiddleware(inner)