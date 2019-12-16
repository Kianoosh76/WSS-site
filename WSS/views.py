from random import Random
from itertools import groupby
from django.shortcuts import get_object_or_404, render
from django.views.generic.detail import DetailView
from django.http import HttpResponse
from django.shortcuts import redirect
from django.http import Http404
import logging

from events.models import Workshop

logger = logging.getLogger('payment')
from zeep import Client
from django.views.decorators.csrf import csrf_exempt
from WSS.forms import ParticipantForm
from WSS.mixins import FooterMixin, WSSWithYearMixin
from WSS.models import WSS, Participant, Grade, Reserve, ShortLink, ExternalLink


class HomeView(FooterMixin, DetailView):
    template_name = 'WSS/home.html'
    context_object_name = 'wss'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_seminars'] = self.object.non_keynote_seminars.order_by('?')[:8]
        return context

    def get_object(self, queryset=None):
        if 'year' in self.kwargs:
            return get_object_or_404(WSS, year=int(self.kwargs['year']))
        return WSS.objects.first()


class AboutView(FooterMixin, DetailView):
    template_name = 'WSS/about_us.html'
    model = WSS
    context_object_name = 'wss'

    def get_object(self, queryset=None):
        # TODO: I didn't know how to handle this, so I used a simple trick.
        return get_object_or_404(WSS, year=2019)


class SeminarsListView(FooterMixin, DetailView):
    template_name = 'WSS/seminars_list.html'
    model = WSS
    context_object_name = 'wss'

    def get_object(self, queryset=None):
        return get_object_or_404(WSS, year=int(self.kwargs['year']))


class PosterSessionsListView(FooterMixin, DetailView):
    template_name = 'WSS/postersessions_list.html'
    model = WSS
    context_object_name = 'wss'

    def get_object(self, queryset=None):
        return get_object_or_404(WSS, year=int(self.kwargs['year']))


class WorkshopsListView(FooterMixin, DetailView):
    template_name = 'WSS/workshops_list.html'
    model = WSS
    context_object_name = 'wss'

    def get_object(self, queryset=None):
        return get_object_or_404(WSS, year=int(self.kwargs['year']))


class StaffListView(FooterMixin, DetailView):
    template_name = 'WSS/staff_list.html'
    model = WSS
    context_object_name = 'wss'

    def get_object(self, queryset=None):
        return get_object_or_404(WSS, year=int(self.kwargs['year']))


class GalleryImageView(FooterMixin, WSSWithYearMixin, DetailView):
    template_name = 'WSS/gallery_images.html'


class GalleryVideoView(FooterMixin, WSSWithYearMixin, DetailView):
    template_name = 'WSS/gallery_videos.html'


class ScheduleView(FooterMixin, WSSWithYearMixin, DetailView):
    template_name = 'WSS/schedule.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        wss = self.object
        all_events = wss.events.filter(start_time__isnull=False)

        context['pre_wss_events'] = all_events.filter(start_time__date__lt=wss.start_date)
        main_events = all_events.exclude(start_time__date__lt=wss.start_date)

        # Important: I assumed that events with same start_time will have same end_time
        events_by_day = groupby(groupby(main_events, lambda event: event.start_time),
                                lambda group: group[0].date())

        # Surprising bug made me do this! I have know idea why I should reiterate events_by_day!
        context['events_by_day'] = []
        for date, events_by_time in events_by_day:
            print(date)
            _events_by_time = []
            for time, events in events_by_time:
                _events_by_time.append((time, list(events)))  # OMG! casting to list is important!!
            context['events_by_day'].append((date, _events_by_time))
        return context


def compute_cost(participant):
    price = 0
    if participant.participate_in_wss:
        price = other_price
        if participant.is_student:
            price = student_price
    for i in participant.workshops.all():
        price += i.price

    if participant.participate_in_wss:
        for i in participant.workshops.all():
            price -= 10000

    return price


class RegisterView(FooterMixin, WSSWithYearMixin, DetailView):
    template_name = 'WSS/register.html'
    context_object_name = 'wss'
    model = WSS

    def get_object(self, queryset=None):
        return get_object_or_404(WSS, year=int(self.kwargs['year']))

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['form'] = ParticipantForm(initial={'year' :int(self.kwargs['year'])})
        if not self.get_object(self).registration_open:
            context['error'] = "Sorry, the registration has been ended."
        return context


MERCHANT = '5ff4f360-c10a-11e9-af68-000c295eb8fc'
client = Client('https://www.zarinpal.com/pg/services/WebGate/wsdl')
description = "هزینه ثبت نام رویداد wss 2019"
student_price = 170000
other_price = 200000


@csrf_exempt
def send_request(request, year):
    if not get_object_or_404(WSS, year=int(year)).registration_open:
        footer = {
            'past_years': [q[0] for q in
                           WSS.objects.exclude(pk=WSS.active_wss().pk).values_list('year')],
            'external_links': ExternalLink.objects.all()
        }
        return render(request, 'info.html',
                      {'past_years': footer['past_years'], 'external_links': footer['external_links'],
                       'wss': get_object_or_404(WSS, year=year), 'status': 'danger',
                       'info': 'Sorry, the registration has been ended.'})

    form = ParticipantForm(request.POST, initial={'year': year})
    if not form.is_valid():
        return render(request, 'WSS/register.html', {'wss' : get_object_or_404(WSS, year=year), 'form': form, 'error':"Please correct the following errors."})

    CallbackURL = 'http://localhost:8000/' + str(
        year) + '/verify/'  # todo Important: need to edit for realy server.

    current_wss = get_object_or_404(WSS, year=year)
    name = form.cleaned_data['name']
    family = form.cleaned_data['family']
    name_eng = form.cleaned_data['name_english']
    family_eng = form.cleaned_data['family_english']

    email = form.cleaned_data['email']
    age = form.cleaned_data['age']
    grade = form.cleaned_data['grade']
    phone_number = form.cleaned_data['phone_number']
    job = form.cleaned_data['job']
    national_id = form.cleaned_data['national_id']
    university = form.cleaned_data['university']
    introduction_method = form.cleaned_data['introduction_method']
    gender = form.cleaned_data['gender']
    city = form.cleaned_data['city']
    country = form.cleaned_data['country']
    question = form.cleaned_data['question']
    participate_in_wss = form.cleaned_data['participate_in_wss']
    workshops = []
    full_workshops = []
    for i in form.cleaned_data['workshops']:
        workshops.append(i.id)
        if i.capacity <= 0:
            full_workshops.append(i.title)

    if len(full_workshops) > 0:
        ret_error = ""
        for i in full_workshops:
            ret_error += ("Workshop \""+ i.title()+"\" is booked up.\n")

        return render(request, 'WSS/register.html', {'wss': get_object_or_404(WSS, year=year), 'form': form,
                                                 'error': ret_error})
    field_of_interest = ""
    for i in form.cleaned_data['interests']:
        field_of_interest += ", " + i
    is_student = form.cleaned_data['is_student']
    logger.info("participant with email:" + email + " created.")

    try:
        exh = Participant.objects.all().get(email=email)
    except Participant.DoesNotExist:
        exh = None
    if participate_in_wss and exh is not None and exh.payment_status == 'OK':
        return render(request, 'WSS/register.html', {'wss' : get_object_or_404(WSS, year=year), 'form': form, 'error':"You have been registered successfully with this email."})

    try:
        gr = Grade.objects.all().get(level=grade)
    except Grade.DoesNotExist:
        return render(request, 'WSS/register.html', {'wss' : get_object_or_404(WSS, year=year), 'form': form, 'error':"The entered grade is incorrect."})

    cap = gr.capacity
    exh = Participant(current_wss=current_wss, name=name, family=family, email=email, grade=grade,
                      phone_number=phone_number, job=job,
                      university=university, introduction_method=introduction_method, gender=gender,
                      name_english=name_eng, family_english=family_eng,
                      city=city, participate_in_wss=participate_in_wss, age=age,
                      country=country, field_of_interest=field_of_interest, is_student=is_student,
                      national_id=national_id, question=question)
    if participate_in_wss and cap <= 0:
        return reserve(request, exh, year)
        pass

    payment_id = Random().randint(0, 1000000000)
    exh.payment_id = payment_id
    exh.save()
    exh.workshops = workshops
    exh.save()
    price = compute_cost(exh)
    result = client.service.PaymentRequest(MERCHANT, 100, description, email, phone_number,
                                           CallbackURL + email + "/" + str(payment_id))
    if result.Status == 100:
        logger.info("user with email:" + email + " connected to payment")
        return redirect('https://www.zarinpal.com/pg/StartPay/' + str(result.Authority))
    else:
        return HttpResponse('Error code: ' + str(result.Status))  # todo move to error page


@csrf_exempt
def verify(request, year, email, payment_id):
    logger.info("participant with email:" + email + "and payment_id: " + payment_id + " starting to verify.")

    footer = {
        'past_years': [q[0] for q in
         WSS.objects.exclude(pk=WSS.active_wss().pk).values_list('year')],
        'external_links': ExternalLink.objects.all()
    }
    try:
        exh = Participant.objects.all().get(email=email, payment_id=payment_id)
    except Participant.DoesNotExist:
        return render(request, 'info.html', {'past_years': footer['past_years'], 'external_links': footer['external_links'],
                                             'wss' : get_object_or_404(WSS, year=year), 'status':'danger','info': 'Payment was not successful. Please contact support.'}) # todo  move to error page

    price = compute_cost(exh)



    if request.GET.get('Status') == 'OK':
        result = client.service.PaymentVerification(MERCHANT, request.GET['Authority'], price)
        if result.Status == 100:

            exh.payment_status = 'OK'
            exh.save()

            if exh.participate_in_wss:
                gr = Grade.objects.all().get(level=exh.grade)
                gr.capacity -= 1
                gr.save()

            for i in exh.workshops.all():
                exh.payed_workshops.add(i.id)
                i.capacity -= 1
                i.save()


            exh.payed_amount += price
            exh.save()
            logger.info("participant with email:" + email + " verified successfully.")
            return render(request, 'info.html', {'past_years': footer['past_years'], 'external_links': footer['external_links'], 'wss': get_object_or_404(WSS, year=year),
                                                 'status':'success','info': 'You have registered successfully. Your tracking code is:' + str(result.RefID)})  # todo  move to error page
        elif result.Status == 101:
            logger.info(
                "participant with email:" + email + " verified again. perhaps he attacking us.")  # todo redirect to tekrari

            return HttpResponse('Transaction submitted : ' + str(result.Status))
        else:
            logger.info("participant with email:" + email + " don't verified")
            return HttpResponse('Transaction failed.\nStatus: ' + str(result.Status))  # todo redirect to error page
    else:
        logger.info("participant with email:" + email + " don't verified")
        return render(request, 'info.html', {'past_years': footer['past_years'], 'external_links': footer['external_links'],
                                             'wss' : get_object_or_404(WSS, year=year), 'status':'danger', 'info': 'Payment was not successful.'}) # todo  move to error page


def reserve(request, participant, year):
    my_reserve = Reserve(participant)
    my_reserve.save()
    return render(request, 'info.html', {'wss': get_object_or_404(WSS, year=year),
                                         'info': 'Unfortunately, the seminar\'s capacity for your grade is full. We will contact you if the capacity was increased.'})  # todo  move to error page


class NotFound(FooterMixin, WSSWithYearMixin, DetailView):
    template_name = '../templates/404.html'


def go(request, year, url):
    link = None
    try:
        link = ShortLink.objects.all().get(short_link=url)
    except:
        raise Http404
    return redirect(to=link.url)
