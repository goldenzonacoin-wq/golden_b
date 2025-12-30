from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'profiles', views.UserProfileViewSet, basename='userprofile')
router.register(r'activities', views.UserActivityViewSet, basename='useractivity')
router.register(r'organisations', views.OrganisationViewSet)
router.register(r'addresses', views.AddressViewSet,basename='account-address')

urlpatterns = [
    path('', include(router.urls)),
    path("verify/",views.VerificationAPI.as_view(),name="verify"),
    path('countries/', views.CountryListView.as_view(), name='country-list'),
    path('regions/', views.RegionListView.as_view(), name='region-list'),
    path('subregions/', views.SubRegionListView.as_view(), name='subregion-list'),
    path('cities/', views.CityListView.as_view(), name='city-list'),

]
