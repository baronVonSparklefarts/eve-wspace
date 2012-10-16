from Map.models import *
from Map.utils import *
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.template.response import TemplateResponse
from django.core.urlresolvers import reverse
from django.template import RequestContext
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required, permission_required
from datetime import datetime, timedelta
import pytz
# Create your views here.

@login_required()
def get_map(request, mapID="0"):
    """This function takes a request and Map ID, determines if access
    should be permitted and either builds a context and loads map.html
    or raises a 403 error. If the map does not exist, we go back to home.

    Additionally, if the request is AJAX, we treat the request as a check-in
    and update a user's current system if IGB headers are present and pass
    along any new map logs.

    Finally, POST requests may have key values that indicate commands to be processed.

    """
    # If mapID is 0, then a map ID was not passed and we should direct to home
    if mapID == "0":
        return HttpResponseRedirect(reverse('core.views.home_view'))
    # Get the map if it exists. If it doesn't go t`o home page.

    try:
        result = Map.objects.get(pk=mapID)
    except Map.DoesNotExist:
        return HttpResponseRedirect(reverse('core.views.home_view'))
    if request.POST.__contains__('topsystem'):
        # We're trying to add a system. Prepare the values needed.
        topsystem = System.objects.get(name=request.POST.get('topsystem'))
        bottomsystem = System.objects.get(name=request.POST.get('bottomsystem'))
        toptype = WormholeType.objects.get(name=request.POST.get('topwh'))
        bottomtype = WormholeType.objects.get(name=request.POST.get('bottomwh'))
        timestatus = int(request.POST.get('timestatus'))
        massstatus = int(request.POST.get('massstatus'))
        topbubbled = "1" == request.POST.get('topbubbled')
        bottombubbled = "1" == request.POST.get('bottombubbled')
        friendlyname = request.POST.get('friendly')
        topms = MapSystem.objects.filter(system=topsystem, map=result).all()[0]
        # Add System
        bottomms = add_system_to_map(request.user, result, bottomsystem,
                friendlyname, False, topms)
        # Connect the systems with a wormhole
        add_wormhole_to_map(result, topms, toptype, bottomtype, bottomms,
                bottombubbled, timestatus, massstatus, topbubbled)
        
    if request.is_ajax() == False:
        # Check our access for the map. If 0, go to home page.
        permissions = check_map_permission(request.user, result)
        if permissions == 0:
            return HttpResponseRedirect(reverse('core.views.home_view'))
        # Get the context dict
        context = get_map_context(result, request.user)
        return TemplateResponse(request, 'map.html', context)
    else:
        # Initialize json return dict
        jsonvalues = {}
        profile = request.user.get_profile()
        # Out AJAX requests should post a JSON datetime called loadtime
        # back that we use to get recent logs.
        if not request.POST.get("loadtime"):
            return HttpResponse(json.dumps({error: "No loadtime"}),mimetype="application/json")
        timestring = request.POST.get("loadtime")
        if request.is_igb:
            loadtime = datetime.strptime(timestring, '%Y-%m-%dT%H:%M:%SZ')
            loadtime = loadtime.replace(tzinfo=pytz.utc)
            if request.is_igb_trusted:
                # Get values to pass in JSON
                oldsystem = ""
                oldsysobj = None
                if profile.currentsystem:
                    oldsystem = profile.currentsystem.name
                    oldsysobj = System.objects.get(name=oldsystem)
                currentsystem = request.eve_systemname
                currentsysobj = System.objects.get(name=currentsystem)
                # Update the user's current system
                profile.currentsystem = System.objects.get(name=currentsystem)
                # TODO: if currentsystem isn't on the map, oldsystem is, and lastactive
                # is recent, add new system to map
                if profile.lastactive > datetime.utcnow().replace(tzinfo=pytz.utc) - timedelta(minutes=5):
                    if oldsysobj:
                        if oldsystem != currentsystem and system_is_in_map(oldsysobj, result) == True:
                            if system_is_in_map(currentsysobj, result) == False:
                                dialogHtml = render_to_string('igb_system_add_dialog.html',
                                        {'oldsystem': oldsystem, 'newsystem': currentsystem,
                                            'wormholes': get_possible_wormhole_types(oldsysobj, 
                                            currentsysobj)}, context_instance=RequestContext(request))
                                jsonvalues.update({'dialogHTML': dialogHtml})
                profile.lastactive = datetime.utcnow().replace(tzinfo=pytz.utc)
                profile.save()
               
        else:
            loadtime = datetime.strptime(timestring, '%Y-%m-%dT%H:%M:%S.%fZ')
            loadtime.replace(tzinfo=pytz.utc)
        newlogquery = MapLog.objects.filter(timestamp__gt=loadtime).all()
        if len(newlogquery) > 0:
            loglist = []
            for log in newlogquery:
                loglist.append("Time: %s  User: %s Action: %s" % (log.timestamp,
                    log.user.username, log.action))
            logstring = render_to_string('log_div.html', {'logs': loglist})
            jsonvalues.update({'logs': logstring})
        return HttpResponse(json.dumps(jsonvalues), mimetype="application/json")


@login_required()
def view_system(request, action=0):
    """This view returns the HTML to display a system within a div." It should
    be called via an AJAX POST request, but not necessarily from a Map. It uses
    different templates depending on the action vaiable:
    0 = system_ajax.html
    1 = system_menu.html
    2 = system_tooltip.html

    """
    if request.is_ajax():
        if action == 0:
            template = 'system_ajax.html'
        if action == 1:
            template = 'system_menu.html'
        if action == 2:
            template = 'system_tooltip.html'

        sysid = request.POST.get("sysid", "0")
        mapsystem = request.POST.get("mapsystem", None)
        mapsys = None
        if sysid == "0":
            raise Http404
        try:
            result = System.objects.get(pk=sysid)
            threshold = datetime.utcnow().replace(tzinfo=pytz.utc) - timedelta(hours=3)
            print threshold
            if result.lastscanned > threshold:
                scanwarning = False
            else:
                scanwarning = True
            print scanwarning
            if result.sysclass > 6:
                specialsys = KSystem.objects.get(name=result.name)
            else:
                specialsys = WSystem.objects.get(name=result.name)
        except ObjectDoesNotExist:
            raise Http404
        if mapsystem:
            try:
                mapsys = MapSystem.objects.get(pk=mapsystem)
            except ObjectDoesNotExist:
                raise Http404
        return HttpResponse(render_to_string(template, 
            {'system': result, 'mapsys': mapsys, 'specialsys': specialsys,
                'scanwarning': scanwarning}, 
            context_instance=RequestContext(request)))
    else:
        raise PermissionDenied


@login_required()
def wormhole_tooltip(request):
    raise PermissionDenied


@login_required()
def mark_scanned(request):
    """Takes a POST request from AJAX with a system ID and marks that system
    as scanned.

    """
    if request.is_ajax():
        sysid = request.POST.get("sysid",0)
        if sysid == 0:
            raise Http404
        try:
            system = System.objects.get(pk=sysid)
            system.lastscanned = datetime.utcnow().replace(tzinfo=pytz.utc)
            system.save()
            return HttpResponse('[]')
        except DoesNotExist:
            raise Http404
    else:
        raise PermissionDenied

@permission_required('Map.add_Map')
def create_map(request):
    """This function creates a map and then redirects to the new map.

    """
    if request.method == 'POST':
        form = MapForm(request.POST)
        if form.is_valid():
            newMap = form.save()
            add_log(request.user, newMap, "Created the %s map." % (newMap.name))
            add_system_to_map(request.user, newMap, newMap.root, "Root", True, None)
            return HttpResponseRedirect(reverse('Map.views.get_map', 
                kwargs={'mapID': newMap.pk }))
    else:
        form = MapForm
        return TemplateResponse(request, 'new_map.html', { 'form': form, })

