# chat/chatbot_logic.py
import os
import time
import asyncio # Import asyncio
from openai import OpenAI
from .models import ChatHistory, Product # Import your models
# from django.apps import apps # Might not be needed if you pass necessary data directly

# Initialize OpenAI client once (or handle in consumer if per-connection needed)
# For simplicity, let's assume env var is set and initialize globally or pass API key
# client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
# assistant_id = os.environ.get("OPENAI_ASSISTANT_ID")

# You need an async function to load/create the thread, similar to views.handle_thread
async def load_or_create_openai_thread_async(user):
    # Get the current event loop
    loop = asyncio.get_event_loop()
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY")) # Initialize here if not global

    # Run synchronous DB query in a thread pool
    chat_history_entry = await loop.run_in_executor(
        None, # Use default thread pool
        lambda: ChatHistory.objects.filter(user=user, thread_id__isnull=False).first()
    )

    thread_id = chat_history_entry.thread_id if chat_history_entry else None
    print(f"Retrieved Thread ID from DB: {thread_id}")

    if not thread_id:
        print("Creating new thread...")
        # Run synchronous OpenAI call in a thread pool
        thread = await loop.run_in_executor(
            None,
            lambda: client.beta.threads.create()
        )
        thread_id = thread.id
        print(f"New Thread Created: {thread_id}")

        # Store the new thread_id in the database (sync DB call in thread pool)
        await loop.run_in_executor(
            None,
            lambda: ChatHistory.objects.create(user=user, role="system", content="Initial context set", thread_id=thread_id)
        )

        # Fetch available products (sync DB call in thread pool)
        available_products = await loop.run_in_executor(
            None,
            lambda: list(Product.objects.values_list('name', flat=True))
        )
        print(f"Available Products: {list(available_products)}")

        products_formatted = "\n".join([f"- {product}" for product in available_products])

        # Prepare and send initial context message (sync OpenAI call in thread pool)
        initial_context_message = f"""You are a helpful AI assistant for suggesting products. Your goal is to suggest relevant products from the following list: {', '.join(available_products)}. When the user asks for product suggestions, understand the category and suggest up to 3 products. Format your response with "**Response:**" followed by your conversational answer, and then "**Suggested Products:**" followed by a bulleted list of product names. Remember the user's name if provided.\n\nAvailable Products:\n{products_formatted}"""
        print(f"Initial Context Message:\n{initial_context_message}")

        await loop.run_in_executor(
            None,
            lambda: client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=initial_context_message,
            )
        )
        print("Initial Context Sent to Assistant.")
    else:
        print("Using existing thread from database.")

    return thread_id # Return the thread_id


# This async function replaces the core logic inside SendMessageView.post
async def process_voice_transcript(user, user_message, thread_id):
    # Get the current event loop
    loop = asyncio.get_event_loop()
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY")) # Initialize here if not global
    assistant_id = os.environ.get("OPENAI_ASSISTANT_ID") # Initialize here if not global

    print(f"Processing message with Assistant: {user_message} for thread: {thread_id}")

    # --- Add Current User Message (sync OpenAI call in thread pool) ---
    # Use the augmented message structure you had in SendMessageView
    new_message_content = f"""users message : {user_message} note : if the user asks for product suggestions, understand the category and suggest up to 3 products else if not asked for product give info they needed but at end try ask if any product is requied. Format your response with **Response:** followed by your conversational answer, and then **Suggested Products:** followed by a bulleted list of product names, remember the format. if not asked for product act as general bot and tell what is asked for. After bulleted list of product names do not add any info and info in responce and maintain format"""

    await loop.run_in_executor(
         None,
         lambda: client.beta.threads.messages.create(
             thread_id=thread_id,
             role="user",
             content=new_message_content,
         )
     )

    # Save user message to database (sync DB call in thread pool)
    await loop.run_in_executor(
         None,
         lambda: ChatHistory.objects.create(
             user=user,
             role="user",
             content=user_message, # Save original user message
             thread_id=thread_id
         )
    )
    print("User message added to thread and saved to database.")

    # --- Run the Assistant (sync OpenAI call in thread pool) ---
    print("Running the Assistant...")
    run = await loop.run_in_executor(
        None,
        lambda: client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
        )
    )
    print(f"Run ID: {run.id}, Status: {run.status}")

    # --- Poll for Run Completion (sync OpenAI calls in thread pool) ---
    while run.status not in ["completed", "failed", "cancelled", "expired"]:
        await asyncio.sleep(1) # Use async sleep
        run = await loop.run_in_executor(
            None,
            lambda: client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        )
        print(f"Run Status Updated: {run.status}")

    # --- Retrieve Messages (sync OpenAI call in thread pool) ---
    assistant_messages = await loop.run_in_executor(
        None,
        lambda: client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=1)
    )

    # --- Process Assistant Response (Adapt your existing logic) ---
    chatbot_response = ""
    suggested_products = []
    # Note: initial_suggestions was passed via HTTP POST, you need to rethink
    # how suggestions are handled in the voice flow. Maybe they aren't needed
    # via the voice channel response, or you send them as a separate message?
    # For now, we'll ignore initial_suggestions as it came from the HTTP view.
    initial_suggestions = [] # Placeholder - Adapt as needed

    if assistant_messages.data:
        latest_message = assistant_messages.data[0]
        if latest_message.role == "assistant":
            # OpenAI Assistants API content can be complex; this assumes text
            if latest_message.content and latest_message.content[0].type == 'text':
                full_response = latest_message.content[0].text.value
                print(f"Latest Assistant Response: {full_response}")

                # Your parsing logic for "**Response:**" and "**Suggested Products:**"
                suggestion_heading_plural = '**Suggested Products:**'
                suggestion_heading_singular = '**Suggested Product:**'

                if suggestion_heading_plural in full_response:
                    parts = full_response.split(suggestion_heading_plural, 1) # Split only once
                    chatbot_response = parts[0].replace('**Response:**', '').strip()
                    suggestions_text = parts[1].strip() if len(parts) > 1 else ""
                elif suggestion_heading_singular in full_response:
                    parts = full_response.split(suggestion_heading_singular, 1) # Split only once
                    chatbot_response = parts[0].replace('**Response:**', '').strip()
                    suggestions_text = parts[1].strip() if len(parts) > 1 else ""
                else:
                    # No suggestion heading found, the whole response is the chat part
                    chatbot_response = full_response.replace('**Response:**', '').strip()
                    suggestions_text = "" # No suggestions found

                if suggestions_text:
                    # Parse the suggested product list
                    suggestion_lines = [line.strip().lstrip('- ').strip() for line in suggestions_text.split('\n') if line.strip().startswith('-')]
                    # Need to retrieve available products list (sync DB call in thread pool)
                    available_product_names = await loop.run_in_executor(
                        None,
                        lambda: list(Product.objects.values_list('name', flat=True))
                    )
                    # Filter suggestions against actual product names
                    suggested_products = []
                    for name in suggestion_lines:
                        cleaned_name = name.strip()
                        if cleaned_name in available_product_names:
                            # Fetch category if needed (sync DB call in thread pool)
                            product_obj = await loop.run_in_executor(None, lambda: Product.objects.filter(name=cleaned_name).first())
                            suggested_products.append({
                                "name": cleaned_name,
                                "category": product_obj.category if product_obj else None
                            })
                            if len(suggested_products) >= 3: # Limit to 3
                                break
                    # Corrected indentation for this print statement
                    print(f"Filtered Suggested Products: {suggested_products}")

            else: # Handle non-text content if necessary
                chatbot_response = "Received non-text response from assistant."
                print(f"Assistant response is not text: {latest_message.content}")

    # Optional: Save assistant response to DB if desired (sync DB call in thread pool)
    # await loop.run_in_executor(
    #      None,
    #      lambda: ChatHistory.objects.create(
    #          user=user,
    #          role="assistant",
    #          content=chatbot_response, # Or full_response
    #          thread_id=thread_id # Link to the same thread
    #      )
    # )

    # Return the text response and suggestions
    return {"response": chatbot_response, "suggested_products": suggested_products}