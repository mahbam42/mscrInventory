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
from mscrInventory.views.orders import orders_dashboard_view
from mscrInventory.views.reporting import reporting_dashboard_view
# top level views.py
from mscrInventory import app_views
# from mscrInventory.views import dashboard_view
from mscrInventory.views.imports import (
    create_unmapped_item,
    bulk_unmapped_action,
    ignore_unmapped_item,
    imports_dashboard_view,
    link_unmapped_item,
    upload_square_view,
    fetch_shopify_view,
    unmapped_items_view,
    import_logs_view,
)
#from mscrInventory.views import recipes_modal
from mscrInventory.views.recipe_modal import (
    add_recipe_ingredient,
    confirm_recipes_import,
    create_product_modal,
    delete_recipe_ingredient,
    download_recipes_template,
    edit_product_modal,
    edit_recipe_view,
    export_recipes_csv,
    extend_recipe,
    import_recipes_csv,
    import_recipes_modal,
    recipes_dashboard_view,
    recipes_table_fragment,
    save_recipe_modifiers,
    update_recipe_item,
)
from mscrInventory.views.modifiers import (
    confirm_modifiers_import,
    create_modifier,
    download_modifiers_template,
    edit_modifier_extra_view,
    export_modifiers_csv,
    import_modifiers_csv,
    import_modifiers_modal,
    modifier_rules_modal,
    modifier_explorer_view,
    create_modifier_alias,
)
from mscrInventory.views.inventory import inventory_dashboard_view, add_case, bulk_add_stock, update_ingredient, bulk_add_modal, inventory_low_stock_partial, inventory_all_ingredients_partial, ingredient_details, export_inventory_csv, import_inventory_csv, import_inventory_modal, confirm_inventory_import, download_inventory_csv_template

# from mscrInventory.views.imports import imports_dashboard_view, upload_square_upload, fetch_shopify_view


urlpatterns = [
    path('admin/', admin.site.urls),
    path("__reload__/", include("django_browser_reload.urls")),

    # main dashboard
    path("dashboard/", dashboard_view, name="dashboard"),
    path("reports/", reporting_dashboard_view, name="reporting_dashboard"),
    path("orders/", orders_dashboard_view, name="orders_dashboard"),

    # edit unmapped products and ingredients
    path("partials/unmapped-products/", app_views.unmapped_products_partial, name="unmapped_products_partial"),
    path("partials/unmapped-ingredients/", app_views.unmapped_ingredients_partial, name="unmapped_ingredients_partial"),
    path("partials/empty-modal/", app_views.empty_modal_partial, name="empty_modal_partial"),

    #imports
    path("imports/", imports_dashboard_view, name="imports_dashboard"),
    path("imports/upload-square/", upload_square_view, name="upload_square"),
    path("imports/unmapped-items/", unmapped_items_view, name="imports_unmapped_items"),
    path("imports/logs/", import_logs_view, name="import_logs"),
    path("dashboard/unmapped/", unmapped_items_view, name="imports_unmapped_dashboard"),
    path("imports/unmapped-items/<int:pk>/link/", link_unmapped_item, name="imports_unmapped_link"),
    path(
        "imports/unmapped-items/<int:pk>/create/",
        create_unmapped_item,
        name="imports_unmapped_create",
    ),
    path(
        "imports/unmapped-items/<int:pk>/ignore/",
        ignore_unmapped_item,
        name="imports_unmapped_ignore",
    ),
    path(
        "imports/unmapped-items/bulk-action/",
        bulk_unmapped_action,
        name="imports_unmapped_bulk",
    ),
    path("imports/fetch-shopify/", fetch_shopify_view, name="fetch_shopify"),

    #recipes
    path("recipes/", recipes_dashboard_view, name="recipes_dashboard"),
    path("recipes/<int:pk>/edit/", edit_recipe_view, name="edit_recipe"),
    path("recipes/<int:pk>/edit-product/", edit_product_modal, name="recipes_edit_product"),
    path("recipes/<int:pk>/add-ingredient/", add_recipe_ingredient, name="add_recipe_ingredient"),
    path("recipes/<int:pk>/save-modifiers/", save_recipe_modifiers, name="save_recipe_modifiers"),
    path("recipes/<int:product_id>/delete-ingredient/<int:item_id>/", delete_recipe_ingredient, name="delete_recipe_ingredient"),
    path("recipes/table/", recipes_table_fragment, name="recipes_table_fragment"),
    path("recipes/<int:pk>/extend/", extend_recipe, name="extend_recipe"),
    path("recipes/item/<int:pk>/update/", update_recipe_item, name="update_recipe_item"),
    path("recipes/products/new/", create_product_modal, name="recipes_create_product"),
    path("modifiers/rules/", modifier_rules_modal, name="modifier_rules_modal"),
    path("modifiers/create/", create_modifier, name="create_modifier"),
    path("modifiers/<int:modifier_id>/edit-extra/", edit_modifier_extra_view, name="edit_modifier_extra"),
    path("modifiers/export/", export_modifiers_csv, name="export_modifiers_csv"),
    path("modifiers/import/modal/", import_modifiers_modal, name="import_modifiers_modal"),
    path("modifiers/import/", import_modifiers_csv, name="import_modifiers_csv"),
    path("modifiers/import/confirm/", confirm_modifiers_import, name="confirm_modifiers_import"),
    path("modifiers/import/template/", download_modifiers_template, name="download_modifiers_template"),
    path("modifiers/explorer/", modifier_explorer_view, name="modifier_explorer"),
    path("modifiers/aliases/create/", create_modifier_alias, name="modifier_alias_create"),
    path("recipes/export/", export_recipes_csv, name="export_recipes_csv"),
    path("recipes/import/modal/", import_recipes_modal, name="import_recipes_modal"),
    path("recipes/import/", import_recipes_csv, name="import_recipes_csv"),
    path("recipes/import/confirm/", confirm_recipes_import, name="confirm_recipes_import"),
    path("recipes/import/template/", download_recipes_template, name="download_recipes_template"),

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
