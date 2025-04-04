import os
from openai import OpenAI
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny  # Import AllowAny
from rest_framework.renderers import TemplateHTMLRenderer
from .models import ChatHistory, Product
import os
from openai import OpenAI
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from .models import ChatHistory, Product
import time
import os
import time
from openai import OpenAI
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .models import ChatHistory, Product
from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.text_splitter import CharacterTextSplitter
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from django.apps import apps

class ChatView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'chat/chat_window.html'

    def get_permissions(self):
        return [AllowAny()]

    def get_authenticators(self):
        return []

    def get(self, *args, **kwargs):
        return Response()
    
class SuggestionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        messages = ChatHistory.objects.filter(user=user, role="user").order_by('-timestamp')[:15].values('role', 'content')

        print("chat history" , messages)

        if not messages:
            return Response({"suggestions": []}, status=status.HTTP_200_OK)

        available_product_names_queryset = Product.objects.values_list('name', flat=True)
        print("available_product_names" , available_product_names_queryset)
        available_product_names_list = [str(name).strip().lower() for name in available_product_names_queryset]

        prompt_content = f"""You are an AI assistant designed to suggest products to users based on their past chat history. Your goal is to provide up to 4 relevant product names from the following list of available products: {', '.join(available_product_names_queryset)}.

Consider the user's past chat history to understand their interests and preferences. If the chat history does not provide clear product interests, suggest general popular products from the available list.

Chat History:
{[msg['content'] for msg in messages]}

Provide your suggestions as a numbered list of product names. If you cannot find any suitable products, return an empty list.
Product Suggestions:"""

        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        try:
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt_content}],
                max_tokens=150,
                n=1,
                stop=None,
                temperature=0.6,
            )
            print(response)
            suggestion_text = response.choices[0].message.content.strip()
            suggested_lines = suggestion_text.split('\n')
            suggested_product_names = []
            for line in suggested_lines:
                line = line.strip()
                if line.startswith(('1.', '2.', '3.', '4.')):
                    parts = line.split('.', 1)[1].strip()
                    parts = parts.replace('\xa0', ' ')
                    if ' -' in parts:
                        product_name = parts.split(' -')[0].strip()
                    else:
                        product_name = parts.strip()

                    # Remove markdown bold formatting
                    if product_name.startswith('**') and product_name.endswith('**'):
                        product_name = product_name[2:-2].strip()

                    suggested_product_names.append(product_name)

            print("Extracted suggested_product_names:", suggested_product_names) # Add this for debugging

            valid_suggestions = []
            for name in suggested_product_names:
                cleaned_suggested_name = name.strip().lower()
                if cleaned_suggested_name in available_product_names_list:
                    valid_suggestions.append({"name": name.strip()})

            print(valid_suggestions)
            return Response({"suggestions": valid_suggestions[:4]}, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error getting suggestions from OpenAI: {e}")
            return Response({"suggestions": []}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)        


class SendMessageView(APIView):
    def retrieve_relevant_info(self, query, retriever, llm):
        prompt_template = """Use the following pieces of context to answer the user's question. If you don't know the answer, just say that you don't know, don't try to make up an answer.

        Context:
        {context}

        Question: {question}"""
        PROMPT = PromptTemplate(
            template=prompt_template, input_variables=["context", "question"]
        )

        qa = RetrievalQA.from_chain_type(
            llm=apps.get_app_config('chat').llm,
            chain_type="stuff",
            retriever=apps.get_app_config('chat').retriever,
            return_source_documents=False,
            chain_type_kwargs={"prompt": PROMPT}
        )
        result = qa({"query": query})
        return result['result']

    def handle_thread(self, user, client):
        chat_history_entry = ChatHistory.objects.filter(user=user, thread_id__isnull=False).first()
        thread_id = chat_history_entry.thread_id if chat_history_entry else None
        print(f"Retrieved Thread ID from DB: {thread_id}")

        if not thread_id:
            print("Creating new thread...")
            thread = client.beta.threads.create()
            thread_id = thread.id
            print(f"New Thread Created: {thread_id}")
            ChatHistory.objects.create(user=user, role="system", content="Initial context set", thread_id=thread_id)

            available_products = Product.objects.values_list('name', flat=True)
            print(f"Available Products: {list(available_products)}")
            products_formatted = "\n".join([f"- {product}" for product in available_products])
            initial_context_message = f"""You are a helpful AI assistant for suggesting products. Your goal is to suggest relevant products from the following list: {', '.join(available_products)}. When the user asks for product suggestions, understand the category and suggest up to 3 products. Format your response with "**Response:**" followed by your conversational answer, and then "**Suggested Products:**" followed by a bulleted list of product names. Remember the user's name if provided.\n\nAvailable Products:\n{products_formatted}"""
            print(f"Initial Context Message:\n{initial_context_message}")
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=initial_context_message,
            )
            print("Initial Context Sent to Assistant.")
        else:
            print("Using existing thread from database.")
        return thread_id

    def send_message_to_assistant(self, client, thread_id, message):
        print(f"Sending to Assistant: {message}")
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message,
        )
        print("User Message Added to Thread.")

    def save_user_message(self, user, message, thread_id):
        ChatHistory.objects.create(
            user=user,
            role="user",
            content=message,
            thread_id=thread_id
        )
        print("User message saved to database.")

    def run_assistant(self, client, thread_id, assistant_id):
        print("Running the Assistant...")
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
        )
        print(f"Run ID: {run.id}, Status: {run.status}")

        while run.status not in ["completed", "failed", "cancelled", "expired"]:
            time.sleep(1)
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            print(f"Run Status Updated: {run.status}")

        assistant_messages = client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=1)
        return assistant_messages

    def process_assistant_response(self, assistant_messages, initial_suggestions):
        chatbot_response = ""
        suggested_products = []
        if assistant_messages.data:
            latest_message = assistant_messages.data[0]
            if latest_message.role == "assistant":
                full_response = latest_message.content[0].text.value
                print(f"Latest Assistant Response: {full_response}")

                suggestion_heading_plural = '**Suggested Products:**'
                suggestion_heading_singular = '**Suggested Product:**'

                if suggestion_heading_plural in full_response:
                    parts = full_response.split(suggestion_heading_plural)
                    chatbot_response = parts[0].replace('**Response:**', '').strip()
                    suggestions_text = parts[1].strip()
                elif suggestion_heading_singular in full_response:
                    parts = full_response.split(suggestion_heading_singular)
                    chatbot_response = parts[0].replace('**Response:**', '').strip()
                    suggestions_text = parts[1].strip()
                else:
                    chatbot_response = full_response.replace('**Response:**', '').strip()
                    suggestions_text = "" # No suggestions found

                print(f"Extracted Chatbot Response: {chatbot_response}")

                if suggestions_text:
                    suggestion_lines = [line.strip().lstrip('- ').strip() for line in suggestions_text.split('\n') if line.strip().startswith('-')]
                    print(f"Raw Suggested Product Lines: {suggestion_lines}")
                    available_product_names = list(Product.objects.values_list('name', flat=True))
                    suggested_products = [{"name": name, "category": Product.objects.filter(name=name).first().category if Product.objects.filter(name=name).first() else None} for name in suggestion_lines if name in available_product_names and name not in initial_suggestions][:3]
                    print(f"Filtered Suggested Products: {suggested_products}")
        return {"response": chatbot_response, "suggested_products": suggested_products}

    def create_augmented_message(self, user_message, retrieved_info):
        augmented_message = f"users message : {user_message}. Here is some relevant product information: {retrieved_info} note : if the user asks for product suggestions, understand the category and suggest up to 3(three) products else if not asked for product give info they needed but at end try ask if any product is requied. Format your response with **Response:** followed by your conversational answer, and then **Suggested Products:** followed by a bulleted list of product names, remember the format. if not asked for product act as general bot and tell what is asked for. After bulleted list of product names do not add any info and info in responce and maintain format"
        return augmented_message

    def post(self, request, *args, **kwargs):
        user = request.user
        user_message = request.data.get('message')
        initial_suggestions = request.data.get('initial_suggestions', [])

        print(f"User: {user.username}, Message Received: {user_message}")

        if not user_message:
            print("Error: Message is required")
            return Response({"error": "Message is required"}, status=status.HTTP_400_BAD_REQUEST)

        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        assistant_id = os.environ.get("OPENAI_ASSISTANT_ID")
        print(f"Assistant ID: {assistant_id}")

        chat_app_config = apps.get_app_config('chat')
        retriever = chat_app_config.retriever
        llm = chat_app_config.llm

        retrieved_info = self.retrieve_relevant_info(user_message, retriever, llm)

        thread_id = self.handle_thread(user, client)

        augmented_message = self.create_augmented_message(user_message, retrieved_info)
        self.send_message_to_assistant(client, thread_id, augmented_message)
        self.save_user_message(user, user_message, thread_id)

        assistant_messages = self.run_assistant(client, thread_id, assistant_id)
        response_data = self.process_assistant_response(assistant_messages, initial_suggestions)

        return Response(response_data, status=status.HTTP_200_OK)
    
    
#------implementation without langChain using OpenAi Assistant API
# class SendMessageView(APIView):
#     authentication_classes = [JWTAuthentication]
#     permission_classes = [IsAuthenticated]

#     def post(self, request, *args, **kwargs):
#         user = request.user
#         user_message = request.data.get('message')
#         initial_suggestions = request.data.get('initial_suggestions', [])

#         print(f"User: {user.username}, Message Received: {user_message}")

#         if not user_message:
#             print("Error: Message is required")
#             return Response({"error": "Message is required"}, status=status.HTTP_400_BAD_REQUEST)

#         client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
#         assistant_id = os.environ.get("OPENAI_ASSISTANT_ID")
#         print(f"Assistant ID: {assistant_id}")

#         # --- Check if a thread_id exists for the user ---
#         chat_history_entry = ChatHistory.objects.filter(user=user, thread_id__isnull=False).first()
#         thread_id = chat_history_entry.thread_id if chat_history_entry else None
#         print(f"Retrieved Thread ID from DB: {thread_id}")

#         if not thread_id:
#             print("Creating new thread...")
#             thread = client.beta.threads.create()
#             thread_id = thread.id
#             print(f"New Thread Created: {thread_id}")
#             # --- Store the new thread_id in the database ---
#             ChatHistory.objects.create(user=user, role="system", content="Initial context set", thread_id=thread_id)

#             available_products = Product.objects.values_list('name', flat=True)
#             print(f"Available Products: {list(available_products)}")

#             products_formatted = "\n".join([f"- {product}" for product in available_products])

#             initial_context_message = f"""You are a helpful AI assistant for suggesting products. Your goal is to suggest relevant products from the following list: {', '.join(available_products)}. When the user asks for product suggestions, understand the category and suggest up to 3 products. Format your response with "**Response:**" followed by your conversational answer, and then "**Suggested Products:**" followed by a bulleted list of product names. Remember the user's name if provided.

# Past Conversation History:\n\nAvailable Products:\n{products_formatted}"""
#             print(f"Initial Context Message:\n{initial_context_message}")
#             client.beta.threads.messages.create(
#                 thread_id=thread_id,
#                 role="user",
#                 content=initial_context_message,
#             )
#             print("Initial Context Sent to Assistant.")
#         else:
#             print("Using existing thread from database.")

#         # --- Add Current User Message ---
#         print(f"Sending to Assistant: {user_message}")
#         new_message = f"users message : {user_message} note : if the user asks for product suggestions, understand the category and suggest up to 3 products else if not asked for product give info they needed but at end try ask if any product is requied. Format your response with **Response:** followed by your conversational answer, and then **Suggested Products:** followed by a bulleted list of product names, remember the format. if not asked for product act as general bot and tell what is asked for. After bulleted list of product names do not add any info and info in responce and maintain format"
#         client.beta.threads.messages.create(
#             thread_id=thread_id,
#             role="user",
#             content=new_message,
#         )
#         ChatHistory.objects.create(
#             user=user,
#             role="user",
#             content=user_message,
#             thread_id=thread_id
#         )
#         print("User Message Added to Thread.")

#         # --- Run the Assistant ---
#         print("Running the Assistant...")
#         run = client.beta.threads.runs.create(
#             thread_id=thread_id,
#             assistant_id=assistant_id,
#         )
#         print(f"Run ID: {run.id}, Status: {run.status}")

#         while run.status not in ["completed", "failed", "cancelled", "expired"]:
#             time.sleep(1)
#             run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
#             print(f"Run Status Updated: {run.status}")

#         assistant_messages = client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=1) 
#         chatbot_response = ""
#         suggested_products = []
#         if assistant_messages.data:
#             latest_message = assistant_messages.data[0]
#             if latest_message.role == "assistant":
#                 full_response = latest_message.content[0].text.value
#                 print(f"Latest Assistant Response: {full_response}")

#                 suggestion_heading_plural = '**Suggested Products:**'
#                 suggestion_heading_singular = '**Suggested Product:**'

#                 if suggestion_heading_plural in full_response:
#                     parts = full_response.split(suggestion_heading_plural)
#                     chatbot_response = parts[0].replace('**Response:**', '').strip()
#                     suggestions_text = parts[1].strip()
#                 elif suggestion_heading_singular in full_response:
#                     parts = full_response.split(suggestion_heading_singular)
#                     chatbot_response = parts[0].replace('**Response:**', '').strip()
#                     suggestions_text = parts[1].strip()
#                 else:
#                     chatbot_response = full_response.replace('**Response:**', '').strip()
#                     suggestions_text = "" # No suggestions found

#                 print(f"Extracted Chatbot Response: {chatbot_response}")

#                 if suggestions_text:
#                     suggestion_lines = [line.strip().lstrip('- ').strip() for line in suggestions_text.split('\n') if line.strip().startswith('-')]
#                     print(f"Raw Suggested Product Lines: {suggestion_lines}")
#                     available_product_names = list(Product.objects.values_list('name', flat=True))
#                     suggested_products = [{"name": name, "category": Product.objects.filter(name=name).first().category if Product.objects.filter(name=name).first() else None} for name in suggestion_lines if name in available_product_names and name not in initial_suggestions][:3] # Increased limit to 3
#                     print(f"Filtered Suggested Products: {suggested_products}")

#         response_data = {"response": chatbot_response, "suggested_products": suggested_products}
#         print(f"Final Response Data: {response_data}")
#         return Response(response_data, status=status.HTTP_200_OK)