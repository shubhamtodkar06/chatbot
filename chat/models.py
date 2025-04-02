from django.db import models
from django.contrib.auth.models import User

class Product(models.Model):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, choices=[
        ('Furniture', 'Furniture'),
        ('Shoes', 'Shoes'),
        ('Clothes', 'Clothes'),
        ('Perfumes', 'Perfumes'),
    ])
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image_url = models.URLField(null=True, blank=True)
    def __str__(self):
        return self.name

class ChatHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    role = models.CharField(max_length=10, choices=[
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ])
    content = models.TextField()
    thread_id = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.timestamp} - {self.role}"