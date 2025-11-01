from django.urls import path
from . import views

urlpatterns = [
    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/add/', views.ProductCreateView.as_view(), name='product-add'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('products/<int:pk>/edit/', views.ProductUpdateView.as_view(), name='product-edit'),
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('boms/', views.BOMListView.as_view(), name='bom-list'),
    path('boms/create/', views.BOMCreateView.as_view(), name='bom-create'),
    path('boms/<int:pk>/', views.BOMPreviewView.as_view(), name='bom-detail'),
    path('boms/<int:pk>/activate/', views.BOMActivateView.as_view(), name='bom-activate'),
    path('boms/calculate-cost/', views.BOMCostCalculationView.as_view(), name='bom-calculate-cost'),
]