# chat/chatbot_logic.py
import os
import time
import asyncio # Import asyncio
from openai import OpenAI
from .models import ChatHistory, Product # Import your models
# from django.apps import apps # Might not be needed if you pass necessary data directly

# --- UNIQUE PRINT STATEMENT TO VERIFY FILE LOADING ---
print("--- Loading chat/chatbot_logic.py (Version 2) ---")
# -----------------------------------------------------------------------

# Initialize OpenAI client globally (or handle in consumer if per-connection needed)
# For simplicity, let's assume env var is set and initialize globally or pass API key
# It's generally better to initialize clients within async functions or consumers
# as shown in google_cloud_voice.py for better async compatibility, but for
# synchronous parts run via run_in_executor, a global client might be okay.
# Let's stick to initializing within the async functions for consistency.
# client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
# assistant_id = os.environ.get("OPENAI_ASSISTANT_ID")


# You need an async function to load/create the thread, similar to views.handle_thread
async def load_or_create_openai_thread_async(user):
    """
    Loads an existing OpenAI Assistant thread ID for a user or creates a new one.
    Handles synchronous database and OpenAI calls using run_in_executor.
    """
    # Get the current event loop
    loop = asyncio.get_event_loop()
    # Initialize OpenAI client here to ensure it's in an appropriate context
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY")) # Initialize here

    print(f"chatbot_logic: Attempting to load or create thread for user: {user.username}") # Add log

    # Run synchronous DB query in a thread pool
    try:
        chat_history_entry = await loop.run_in_executor(
            None, # Use default thread pool
            lambda: ChatHistory.objects.filter(user=user, thread_id__isnull=False).order_by('-timestamp').first() # Order by timestamp to get latest
        )
        thread_id = chat_history_entry.thread_id if chat_history_entry else None
        print(f"chatbot_logic: Retrieved Thread ID from DB: {thread_id}") # Add log

    except Exception as e:
        print(f"chatbot_logic: Error retrieving thread from DB: {e}") # Add log
        thread_id = None # Ensure thread_id is None on DB error


    if not thread_id:
        print("chatbot_logic: No existing thread found. Creating new thread...") # Add log
        try:
            # Run synchronous OpenAI call in a thread pool
            thread = await loop.run_in_executor(
                None,
                lambda: client.beta.threads.create()
            )
            thread_id = thread.id
            print(f"chatbot_logic: New Thread Created: {thread_id}") # Add log

            # Store the new thread_id in the database (sync DB call in thread pool)
            await loop.run_in_executor(
                None,
                lambda: ChatHistory.objects.create(user=user, role="system", content="Initial context set", thread_id=thread_id)
            )
            print("chatbot_logic: New thread ID saved to database.") # Add log

            # Fetch available products (sync DB call in thread pool)
            available_products = await loop.run_in_executor(
                None,
                lambda: list(Product.objects.values_list('name', flat=True))
            )
            print(f"chatbot_logic: Available Products fetched: {list(available_products)}") # Add log

            products_formatted = "\n".join([f"- {product}" for product in available_products])

            # Prepare and send initial context message (sync OpenAI call in thread pool)
            # Keep your augmented prompt structure
            initial_context_message = f"""You are a helpful AI assistant for suggesting products. Your goal is to suggest relevant products from the following list: {', '.join(available_products)}. When the user asks for product suggestions, understand the category and suggest up to 3 products. Format your response with "**Response:**" followed by your conversational answer, and then "**Suggested Products:**" followed by a bulleted list of product names. Remember the user's name if provided.\n\nAvailable Products:\n{products_formatted}"""
            print(f"chatbot_logic: Initial Context Message:\n{initial_context_message}") # Add log

            await loop.run_in_executor(
                None,
                lambda: client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=initial_context_message,
                )
            )
            print("chatbot_logic: Initial Context Sent to Assistant.") # Add log

        except Exception as e:
            print(f"chatbot_logic: Error creating new thread or sending initial context: {e}") # Add log
            # Depending on severity, you might want to raise the exception
            raise # Re-raise to signal failure

    else:
        print("chatbot_logic: Using existing thread from database.") # Add log

    return thread_id # Return the thread_id

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

# This async function replaces the core logic inside SendMessageView.post
async def process_voice_transcript1(user, user_message, thread_id):
    """
    Processes a user's voice transcript using the OpenAI Assistant.
    Adds message to thread, runs the assistant, retrieves response,
    and parses for text and suggested products.
    Handles synchronous database and OpenAI calls using run_in_executor.
    """
    # Get the current event loop
    loop = asyncio.get_event_loop()
    # Initialize OpenAI client here
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY")) # Initialize here
    assistant_id = os.environ.get("OPENAI_ASSISTANT_ID") # Initialize here

    if not assistant_id:
         print("chatbot_logic: ERROR: OPENAI_ASSISTANT_ID is not set.") # Add log
         return {"response": "Sorry, the AI assistant is not configured correctly.", "suggested_products": []}

    print(f"chatbot_logic: Processing message with Assistant: '{user_message}' for thread: {thread_id}") # Add log

    # --- Add Current User Message (sync OpenAI call in thread pool) ---
    # Use the augmented message structure you had in SendMessageView
    new_message_content = f"""users message : {user_message} note : if the user asks for product suggestions, understand the category and suggest up to 3 products else if not asked for product give info they needed but at end try ask if any product is requied. Format your response with **Response:** followed by your conversational answer, and then **Suggested Products:** followed by a bulleted list of product names, remember the format. if not asked for product act as general bot and tell what is asked for. After bulleted list of product names do not add any info and info in responce and maintain format"""

    try:
        await loop.run_in_executor(
             None,
             lambda: client.beta.threads.messages.create(
                  thread_id=thread_id,
                  role="user",
                  content=new_message_content,
             )
        )
        print("chatbot_logic: User message added to thread.") # Add log

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
        print("chatbot_logic: User message saved to database.") # Add log

        # --- Run the Assistant (sync OpenAI call in thread pool) ---
        print("chatbot_logic: Running the Assistant...") # Add log
        run = await loop.run_in_executor(
            None,
            lambda: client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id,
            )
        )
        print(f"chatbot_logic: Run ID: {run.id}, Status: {run.status}") # Add log

        # --- Poll for Run Completion (sync OpenAI calls in thread pool) ---
        print("chatbot_logic: Polling for run completion...") # Add log
        while run.status not in ["completed", "failed", "cancelled", "expired"]:
            await asyncio.sleep(1) # Use async sleep
            run = await loop.run_in_executor(
                None,
                lambda: client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            )
            print(f"chatbot_logic: Run Status Updated: {run.status}") # Add log

        if run.status != "completed":
             print(f"chatbot_logic: Run did not complete successfully. Final status: {run.status}") # Add log
             return {"response": f"Sorry, the assistant run failed with status: {run.status}", "suggested_products": []}


        # --- Retrieve Messages (sync OpenAI call in thread pool) ---
        print("chatbot_logic: Retrieving messages...") # Add log
        assistant_messages = await loop.run_in_executor(
            None,
            lambda: client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=1)
        )
        print("chatbot_logic: Messages retrieved.") # Add log


        # --- Process Assistant Response (Adapt your existing logic) ---
        chatbot_response = ""
        suggested_products = []

        if assistant_messages.data:
            latest_message = assistant_messages.data[0]
            if latest_message.role == "assistant":
                # OpenAI Assistants API content can be complex; this assumes text
                if latest_message.content and latest_message.content[0].type == 'text':
                    full_response = latest_message.content[0].text.value
                    print(f"chatbot_logic: Latest Assistant Response Text: {full_response}") # Add log

                    # Your parsing logic for "**Response:**" and "**Suggested Products:**"
                    suggestion_heading_plural = '**Suggested Products:**'
                    suggestion_heading_singular = '**Suggested Product:**'
                    response_heading = '**Response:**'

                    # Find the index of the response heading
                    response_start_index = full_response.find(response_heading)
                    if response_start_index != -1:
                        # Extract the part after the response heading
                        content_after_response = full_response[response_start_index + len(response_heading):].strip()

                        # Find the index of the suggestion heading (either plural or singular)
                        suggestion_start_index_plural = content_after_response.find(suggestion_heading_plural)
                        suggestion_start_index_singular = content_after_response.find(suggestion_heading_singular)

                        if suggestion_start_index_plural != -1:
                            # Split by plural heading
                            parts = content_after_response.split(suggestion_heading_plural, 1)
                            chatbot_response = parts[0].strip()
                            suggestions_text = parts[1].strip() if len(parts) > 1 else ""
                        elif suggestion_start_index_singular != -1:
                            # Split by singular heading
                             parts = content_after_response.split(suggestion_heading_singular, 1)
                             chatbot_response = parts[0].strip()
                             suggestions_text = parts[1].strip() if len(parts) > 1 else ""
                        else:
                            # No suggestion heading found after response heading
                            chatbot_response = content_after_response
                            suggestions_text = "" # No suggestions found
                    else:
                         # No Response heading found, treat entire message as response text
                         chatbot_response = full_response.strip()
                         suggestions_text = "" # Assume no structured suggestions if format is off

                    print(f"chatbot_logic: Parsed Chatbot Response: '{chatbot_response}'") # Add log
                    print(f"chatbot_logic: Parsed Suggestions Text: '{suggestions_text}'") # Add log


                    if suggestions_text:
                        # Parse the suggested product list
                        # Look for lines starting with '-'
                        suggestion_lines = [line.strip().lstrip('- ').strip() for line in suggestions_text.split('\n') if line.strip().startswith('-')]
                        print(f"chatbot_logic: Raw Suggestion Lines: {suggestion_lines}") # Add log

                        # Need to retrieve available products list (sync DB call in thread pool)
                        available_product_names = await loop.run_in_executor(
                            None,
                            lambda: list(Product.objects.values_list('name', flat=True))
                        )
                        print(f"chatbot_logic: Available Product Names from DB: {available_product_names}") # Add log

                        # Filter suggestions against actual product names and fetch category
                        suggested_products = []
                        for name in suggestion_lines:
                            cleaned_name = name.strip()
                            # Case-insensitive comparison for robustness
                            matching_product = next((p for p in available_product_names if p.lower() == cleaned_name.lower()), None)

                            if matching_product:
                                # Fetch category (sync DB call in thread pool)
                                product_obj = await loop.run_in_executor(None, lambda: Product.objects.filter(name__iexact=cleaned_name).first()) # Use iexact for case-insensitivity
                                suggested_products.append({
                                    "name": product_obj.name if product_obj else cleaned_name, # Use actual name from DB if found
                                    "category": product_obj.category if product_obj else None
                                })
                                print(f"chatbot_logic: Found matching product: {cleaned_name}") # Add log
                                if len(suggested_products) >= 3: # Limit to 3
                                    print("chatbot_logic: Reached limit of 3 suggested products.") # Add log
                                    break
                            else:
                                print(f"chatbot_logic: No matching product found in DB for suggestion: {cleaned_name}") # Add log

                        print(f"chatbot_logic: Final Filtered Suggested Products: {suggested_products}") # Add log

                else: # Handle non-text content if necessary
                    chatbot_response = "Received non-text response from assistant."
                    print(f"chatbot_logic: Assistant response is not text: {latest_message.content}") # Add log

        print("chatbot_logic: Returning response and suggestions.") # Add log
        return {"response": chatbot_response, "suggested_products": suggested_products}

    except Exception as e:
        print(f"chatbot_logic: Error processing voice transcript with Assistant: {e}") # Add log
        # Re-raise the exception so the caller (consumer) can handle it
        raise


import os
import asyncio
from django.apps import apps  # <-- ADD THIS LINE
from openai import OpenAI
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from chat.models import ChatHistory, Product  # Replace `yourapp` with actual app name
 
async def process_voice_transcript(user, user_message, thread_id):
    """
    Processes a user's voice transcript using a custom prompt-based LLM approach.
    Retrieves relevant info, formats a prompt, calls OpenAI chat completion,
    and extracts structured response and product suggestions.
    """
    try:
        loop = asyncio.get_running_loop()
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        llm = apps.get_app_config('chat').llm
        retriever = apps.get_app_config('chat').retriever

        # --- Retrieve relevant information using retriever ---
        def get_retrieved_info():
            prompt_template = """Use the following pieces of context to answer the user's question. If you don't know the answer, just say that you don't know, don't try to make up an answer.

Context:
{context}

Question: {question}"""
            PROMPT = PromptTemplate(template=prompt_template, input_variables=["context", "question"])
            qa = RetrievalQA.from_chain_type(
                llm=llm,
                chain_type="stuff",
                retriever=retriever,
                return_source_documents=False,
                chain_type_kwargs={"prompt": PROMPT}
            )
            return qa({"query": user_message})["result"]

        retrieved_info = await loop.run_in_executor(None, get_retrieved_info)

        # --- Get conversation history and product list ---
        conversation_history = await loop.run_in_executor(
            None,
            lambda: list(ChatHistory.objects.filter(user=user).order_by('timestamp').values_list('role', 'content'))
        )
        formatted_history = "\n".join([f"{role.capitalize()}: {content}" for role, content in conversation_history])

        available_products = await loop.run_in_executor(
            None,
            lambda: list(Product.objects.values_list('name', flat=True))
        )
        products_formatted = "\n".join([f"- {p}" for p in available_products])

        prompt_content = f"""You are a helpful AI assistant for suggesting products from the following list: {', '.join(available_products)}.

You will be provided with relevant product information and the user's current message, along with the entire conversation history for context. Your goal is to respond to the user's query and suggest up to 3 relevant products.

Format your response with "**Response:**" followed by your conversational answer, and then "**Suggested Products:**" followed by a bulleted list of product names. If no products are relevant, you can omit the "Suggested Products" section.

Relevant Product Information:
{retrieved_info}

Conversation History:
{formatted_history}

Current Message:
User: {user_message}

**Response:** """

        # --- Call OpenAI completion endpoint ---
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt_content}],
                max_tokens=500,
                n=1,
                temperature=0.7,
            )
        )
        full_response = response.choices[0].message.content.strip()
        print(f"chatbot_logic: Full Chatbot Response: {full_response}")

        # --- Parse response and extract suggestions ---
        chatbot_response = full_response
        suggestions_text = ""
        suggested_products = []

        if "**Suggested Products:**" in full_response:
            parts = full_response.split("**Suggested Products:**")
            chatbot_response = parts[0].replace("**Response:**", "").strip()
            suggestions_text = parts[1].strip() if len(parts) > 1 else ""

            suggestion_lines = [line.strip().lstrip('- ').strip() for line in suggestions_text.split('\n') if line.strip().startswith('-')]

            for name in suggestion_lines:
                if name.lower() in [p.lower() for p in available_products]:
                    product_obj = await loop.run_in_executor(
                        None,
                        lambda: Product.objects.filter(name__iexact=name).first()
                    )
                    if product_obj:
                        suggested_products.append({
                            "name": product_obj.name,
                            "category": product_obj.category
                        })
                    if len(suggested_products) >= 3:
                        break

        # --- Save messages to DB ---
        await loop.run_in_executor(
            None,
            lambda: ChatHistory.objects.create(user=user, role="user", content=user_message, thread_id=thread_id)
        )
        await loop.run_in_executor(
            None,
            lambda: ChatHistory.objects.create(user=user, role="assistant", content=chatbot_response, thread_id=thread_id)
        )

        print(f"chatbot_logic: Final Response: {chatbot_response}")
        print(f"chatbot_logic: Suggested Products: {suggested_products}")

        return {"response": chatbot_response, "suggested_products": suggested_products}

    except Exception as e:
        print(f"chatbot_logic: Error processing voice transcript: {e}")
        raise
