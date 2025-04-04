import os
import django

# Configure Django settings if the script is run standalone
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "chatbot_project.settings")  # Replace 'your_project_name' with your project's name
django.setup()

import os
import django



from chat.models import Product

if __name__ == "__main__":
    products_data = [
        # Furniture
        {
            'name': 'Ergonomic Mesh Chair',
            'category': 'Furniture',
            'description': 'Breathable mesh office chair for long hours of work.',
            'price': 229.00,
        },
        {
            'name': 'Round Wooden End Table',
            'category': 'Furniture',
            'description': 'Small and elegant end table for your living space.',
            'price': 79.99,
        },
        {
            'name': 'Standing Desk with Adjustable Height',
            'category': 'Furniture',
            'description': 'Modern standing desk to improve posture and productivity.',
            'price': 349.00,
        },
        {
            'name': 'Loveseat with Throw Pillows',
            'category': 'Furniture',
            'description': 'Comfortable loveseat perfect for small apartments.',
            'price': 399.50,
        },
        {
            'name': 'Wall-Mounted Floating Shelves (Set of 3)',
            'category': 'Furniture',
            'description': 'Space-saving floating shelves for displaying decor.',
            'price': 59.00,
        },
        # Shoes
        {
            'name': 'Trail Running Shoes for Women',
            'category': 'Shoes',
            'description': 'Durable trail running shoes with excellent traction.',
            'price': 95.50,
        },
        {
            'name': 'Suede Loafers for Men',
            'category': 'Shoes',
            'description': 'Stylish and comfortable suede loafers for everyday wear.',
            'price': 85.00,
        },
        {
            'name': 'Ankle Boots with Block Heel',
            'category': 'Shoes',
            'description': 'Fashionable ankle boots with a comfortable block heel.',
            'price': 105.99,
        },
        {
            'name': 'Flip-Flops for Beach and Pool',
            'category': 'Shoes',
            'description': 'Casual and lightweight flip-flops for summer.',
            'price': 19.99,
        },
        {
            'name': 'Work Boots with Steel Toe',
            'category': 'Shoes',
            'description': 'Heavy-duty work boots with steel toe protection.',
            'price': 119.00,
        },
        # Clothes
        {
            'name': 'Organic Cotton Hoodie',
            'category': 'Clothes',
            'description': 'Soft and eco-friendly hoodie made from organic cotton.',
            'price': 49.00,
        },
        {
            'name': 'Slim Fit Chinos',
            'category': 'Clothes',
            'description': 'Versatile slim fit chinos for a smart casual look.',
            'price': 69.50,
        },
        {
            'name': 'Maxi Dress with Floral Print',
            'category': 'Clothes',
            'description': 'Elegant maxi dress with a beautiful floral print.',
            'price': 55.00,
        },
        {
            'name': 'Waterproof Rain Jacket',
            'category': 'Clothes',
            'description': 'Lightweight and waterproof rain jacket for outdoor activities.',
            'price': 79.99,
        },
        {
            'name': 'Polo Shirt with Embroidered Logo',
            'category': 'Clothes',
            'description': 'Classic polo shirt with a subtle embroidered logo.',
            'price': 35.00,
        },
        # Perfumes
        {
            'name': 'Ocean Breeze Eau de Toilette',
            'category': 'Perfumes',
            'description': 'Fresh and aquatic eau de toilette reminiscent of the ocean.',
            'price': 58.00,
        },
        {
            'name': 'Vanilla Blossom Perfume Spray',
            'category': 'Perfumes',
            'description': 'Sweet and comforting perfume with warm vanilla notes.',
            'price': 68.50,
        },
        {
            'name': 'Amber and Leather Cologne',
            'category': 'Perfumes',
            'description': 'Bold and sophisticated cologne with amber and leather accords.',
            'price': 92.00,
        },
        {
            'name': 'Green Tea Scented Mist',
            'category': 'Perfumes',
            'description': 'Light and refreshing body mist with a calming green tea scent.',
            'price': 30.00,
        },
        {
            'name': 'Sandalwood and Patchouli Perfume',
            'category': 'Perfumes',
            'description': 'Earthy and grounding perfume with sandalwood and patchouli.',
            'price': 72.75,
        },
    ]

    # Clear existing products (optional)
    # Product.objects.all().delete()

    for product_data in products_data:
        Product.objects.create(**product_data)

    print("Successfully added a different set of product data to the database.")