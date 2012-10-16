from django.contrib.auth.decorators import login_required
# Create your views here.

@login_required()
def home_view(request):
    """The home view detects whether a user has a default map and either 
    directs them to that map or displays a home page template."""
    from django.contrib.auth.models import User
    from django.core.urlresolvers import reverse
    from Map.models import Map
    from django.template.response import TemplateResponse

    return TemplateResponse(request, 'home.html')
