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
from django.urls import include, path
from django.views.generic import TemplateView
from mscrInventory.views.dashboard import dashboard_view
# top level views.py
from mscrInventory import app_views
# from mscrInventory.views import dashboard_view
from mscrInventory.views.imports import imports_dashboard_view, upload_square_view, fetch_shopify_view
#from mscrInventory.views import recipes_modal
from mscrInventory.views.recipe_modal import export_recipes_csv, import_recipes_csv, recipes_dashboard_view, edit_recipe_view, add_recipe_ingredient, save_recipe_modifiers, delete_recipe_ingredient, recipes_table_fragment, extend_recipe, update_recipe_item
from mscrInventory.views.modifiers import edit_modifier_extra_view
from mscrInventory.views.products import products_dashboard_view
from mscrInventory.views.inventory import inventory_dashboard_view, add_case, bulk_add_stock, update_ingredient, bulk_add_modal, inventory_low_stock_partial, inventory_all_ingredients_partial, ingredient_details, export_inventory_csv, import_inventory_csv, import_inventory_modal, confirm_inventory_import, download_inventory_csv_template

# from mscrInventory.views.imports import imports_dashboard_view, upload_square_upload, fetch_shopify_view


urlpatterns = [
    path('admin/', admin.site.urls),
    path("__reload__/", include("django_browser_reload.urls")),

    # main dashboard 
    path("dashboard/", dashboard_view, name="dashboard"),

    # edit unmapped products and ingredients
    path("partials/unmapped-products/", app_views.unmapped_products_partial, name="unmapped_products_partial"),
    path("partials/unmapped-ingredients/", app_views.unmapped_ingredients_partial, name="unmapped_ingredients_partial"),
    path("partials/empty-modal/", app_views.empty_modal_partial, name="empty_modal_partial"),

    #imports
    path("imports/", imports_dashboard_view, name="imports_dashboard"),
    path("imports/upload-square/", upload_square_view, name="upload_square"),
    path("imports/fetch-shopify/", fetch_shopify_view, name="fetch_shopify"),

    #products
    path("products/", products_dashboard_view, name="products_dashboard"),

    #recipes
    path("recipes/", recipes_dashboard_view, name="recipes_dashboard"),
    path("recipes/<int:pk>/edit/", edit_recipe_view, name="edit_recipe"),
    path("recipes/<int:pk>/add-ingredient/", add_recipe_ingredient, name="add_recipe_ingredient"),
    path("recipes/<int:pk>/save-modifiers/", save_recipe_modifiers, name="save_recipe_modifiers"),
    path("recipes/<int:product_id>/delete-ingredient/<int:item_id>/", delete_recipe_ingredient, name="delete_recipe_ingredient"),
    path("recipes/table/", recipes_table_fragment, name="recipes_table_fragment"),
    path("recipes/<int:pk>/extend/", extend_recipe, name="extend_recipe"),
    path("recipes/item/<int:pk>/update/", update_recipe_item, name="update_recipe_item"),
    path("modifiers/<int:modifier_id>/edit-extra/", edit_modifier_extra_view, name="edit_modifier_extra"),
    path("recipes/export/", export_recipes_csv, name="export_recipes_csv"),
    path("recipes/import/", import_recipes_csv, name="import_recipes_csv"),

    #inventory
    path("inventory/", inventory_dashboard_view, name="inventory_dashboard"),
    path("inventory/update/<int:pk>/", update_ingredient, name="update_ingredient"),
    path("inventory/add_case/<int:pk>/", add_case, name="add_case"),
    path("inventory/bulk_add_stock/", bulk_add_stock, name="bulk_add_stock"),
    path("inventory/bulk_add_modal/", bulk_add_modal, name="inventory_bulk_add_modal"),
    path("inventory/low_stock_partial/", inventory_low_stock_partial, name="inventory_low_stock_partial"),
    path("inventory/all_ingredients_partial/", inventory_all_ingredients_partial, name="inventory_all_ingredients_partial",),
    path("inventory/ingredient/<int:pk>/details/", ingredient_details, name="ingredient_details"),
    path("inventory/export/", export_inventory_csv, name="export_inventory_csv"),
    path("inventory/import/template/", download_inventory_csv_template, name="download_inventory_csv_template"),
    path("inventory/import/", import_inventory_csv, name="import_inventory_csv"),
    path("inventory/import/modal/", import_inventory_modal, name="import_inventory_modal"),
    path("inventory/import/confirm/", confirm_inventory_import, name="confirm_inventory_import"),

]   
