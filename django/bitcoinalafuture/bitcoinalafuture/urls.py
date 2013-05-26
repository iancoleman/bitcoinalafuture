from django.conf.urls import patterns, include, url

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

js_info_dict = {
    'packages': ('thefuture',),
}

urlpatterns = patterns('',
    (r'^$', 'thefuture.views.home'),
    (r'^how_it_works/$', 'thefuture.views.how_it_works'),
    (r'^prediction/(?P<future_price_id>\d+)/(?P<data_type>.*)/$', 'thefuture.views.future_price_detail_api'),
    (r'^prediction/(?P<future_price_id>\d+)/$', 'thefuture.views.future_price_detail'),
    (r'^the_future/$', 'thefuture.views.the_future'),
    (r'^make_new_prediction/$', 'thefuture.views.make_new_prediction'),
    (r'^get_server_time/$', 'thefuture.views.get_server_time'),
    (r'^statistics/$', 'thefuture.views.statistics'),
    (r'^address/(?P<address>.*)/(?P<data_type>.*)/$', 'thefuture.views.address'),
    (r'^contact/$', 'thefuture.views.contact'),
    (r'^api/$', 'thefuture.views.api'),
    (r'^jsi18n/$', 'django.views.i18n.javascript_catalog', js_info_dict),
    (r'^i18n/', include('django.conf.urls.i18n')),
    # Examples:
    # url(r'^$', 'bitcoinalafuture.views.home', name='home'),
    # url(r'^bitcoinalafuture/', include('bitcoinalafuture.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # url(r'^admin/', include(admin.site.urls)),
)
