from django.urls import path
from . import views

urlpatterns = [
    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/add/', views.ProductCreateView.as_view(), name='product-add'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('products/<int:pk>/edit/', views.ProductUpdateView.as_view(), name='product-edit'),
    path('products/<int:pk>/delete/', views.ProductDeleteView.as_view(), name='product-delete'),
    path('products/<int:pk>/transactions/', views.ProductTransactionListView.as_view(), name='product-transactions'),
    path('products/<int:pk>/create-work-order/', views.CreateWorkOrderFromProductView.as_view(), name='create-work-order-from-product'),
    path('products/<int:pk>/deactivate/', views.ProductDeactivateView.as_view(), name='product-deactivate'),
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('boms/', views.BOMListView.as_view(), name='bom-list'),
    path('boms/create/', views.BOMCreateView.as_view(), name='bom-create'),
    path('boms/<int:pk>/', views.BOMPreviewView.as_view(), name='bom-detail'),
    path('boms/<int:pk>/edit/', views.BOMUpdateView.as_view(), name='bom-edit'),
    path('boms/<int:pk>/delete/', views.BOMDeleteView.as_view(), name='bom-delete'),
    path('boms/<int:pk>/new-version/', views.BOMNewVersionView.as_view(), name='bom-new-version'),
    path('boms/<int:pk>/activate/', views.BOMActivateView.as_view(), name='bom-activate'),
    path('boms/<int:pk>/export/', views.BOMExportView.as_view(), name='bom-export'),
    path('boms/calculate-cost/', views.BOMCostCalculationView.as_view(), name='bom-calculate-cost'),
    path('boms/<int:pk>/generate-pick-list/', views.BOMPickListView.as_view(), name='bom-pick-list'),
    path('boms/<int:pk>/cost-analysis/', views.BOMCostAnalysisView.as_view(), name='bom-cost-analysis'),
    path('boms/compare/', views.BOMCompareView.as_view(), name='bom-compare'),
]
