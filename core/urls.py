"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from mscrInventory.views.dashboard import dashboard_view
# from mscrInventory.views import dashboard_view
from mscrInventory.views.imports import imports_dashboard_view, upload_square_view, fetch_shopify_view
from mscrInventory.views import recipes_modal
#from mscrInventory.views.recipes import recipes_dashboard_view, edit_recipe_view, save_recipe_view, add_recipe_ingredient_view, delete_recipe_ingredient_view
from mscrInventory.views.modifiers import edit_modifier_extra_view
from mscrInventory.views.products import products_dashboard_view
from mscrInventory.views.inventory import inventory_dashboard_view

# from mscrInventory.views.imports import imports_dashboard_view, upload_square_upload, fetch_shopify_view


urlpatterns = [
    path('admin/', admin.site.urls),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("imports/", imports_dashboard_view, name="imports_dashboard"),
    path("imports/upload-square/", upload_square_view, name="upload_square"),
    path("imports/fetch-shopify/", fetch_shopify_view, name="fetch_shopify"),
    path("products/", products_dashboard_view, name="products_dashboard"),
#    path("recipes/", recipes_modal.recipes_dashboard_view, name="recipes_dashboard"),
    path("recipes/<int:pk>/edit/", recipes_modal.edit_recipe_modal, name="edit_recipe"),
path("recipes/<int:pk>/add-ingredient/", recipes_modal.add_recipe_ingredient, name="add_recipe_ingredient"),
path("recipes/ingredient/<int:item_id>/delete/", recipes_modal.delete_recipe_ingredient, name="delete_recipe_ingredient"),
path("recipes/<int:pk>/save-modifiers/", recipes_modal.save_recipe_modifiers, name="save_recipe_modifiers"),
#    path("recipes/", recipes_dashboard_view, name="recipes_dashboard"),
#    path("recipes/<int:product_id>/edit/", edit_recipe_view, name="edit_recipe"),
#    path("recipes/<int:product_id>/add-ingredient/", add_recipe_ingredient_view, name="add_recipe_ingredient"),
#    path("recipes/ingredient/<int:ingredient_id>/delete/", delete_recipe_ingredient_view, name="delete_recipe_ingredient"),
#    path("recipes/<int:product_id>/save/", save_recipe_view, name="save_recipe"),
    path("modifiers/<int:modifier_id>/edit-extra/", edit_modifier_extra_view, name="edit_modifier_extra"),
    path("inventory/", inventory_dashboard_view, name="inventory_dashboard"),
]
