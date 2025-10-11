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
from mscrInventory.views.imports import imports_dashboard_view, upload_square_upload, fetch_shopify_view


urlpatterns = [
    path('admin/', admin.site.urls),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("imports/", imports_dashboard_view, name="imports_dashboard"),
    path("imports/upload-square/", upload_square_upload, name="upload_square_csv"),
    path("imports/fetch-shopify/", fetch_shopify_view, name="fetch_shopify_orders"),
]
