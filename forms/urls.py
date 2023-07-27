from django.urls import path, include
from forms import views

urlpatterns = [
    path('<int:user_id>/', views.FormsAllView.as_view(), name='form_list'),
    path('user/<int:pk>', views.FormsUserView.as_view(), name='form_detail'),
    path('qnum/', views.QesNumPostView.as_view(), name='qes_num'),
    path('qnum/<int:form_id>', views.QesNumView.as_view(), name='qes_num'),
]