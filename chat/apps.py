from django.apps import AppConfig


class ChatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chat'
    
    
from django.apps import AppConfig
import os
from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.text_splitter import CharacterTextSplitter

class ChatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chat'  # Replace with your app name

    llm = None
    embeddings = None
    retriever = None

    def initialize_langchain_components(self):
        if self.llm is None:
            self.llm = ChatOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        if self.embeddings is None:
            self.embeddings = OpenAIEmbeddings(api_key=os.environ.get("OPENAI_API_KEY"))
        if self.retriever is None:
            from .models import Product  # Import Product here
            self.retriever = self.load_and_index_products(self.embeddings, Product)

    def load_and_index_products(self, embeddings, Product):
        products = Product.objects.all()
        documents = []
        for product in products:
            documents.append(f"Product Name: {product.name}\nCategory: {product.category}\nDescription: {product.description}")

        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        texts = text_splitter.create_documents(documents)

        db = Chroma.from_documents(texts, embeddings)
        retriever = db.as_retriever(search_kwargs={"k": 2})
        return retriever

    def ready(self):
        super().ready()
        self.initialize_langchain_components()