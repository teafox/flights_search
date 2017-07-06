from calendar import isleap
import datetime
import argparse
import itertools
import collections
import re

import requests
from lxml import html


class InputError(Exception):
    pass


class RequestError(Exception):
    pass


def add_years(d, years):
    new_year = d.year + years
    try:
        return d.replace(year=new_year)
    except ValueError:
        if d.month == 2 and d.day == 29 and isleap(d.year) and not isleap(new_year):
            return d.replace(year=new_year, day=28)
        raise


def validate_input(ticket):
    iata = re.compile('^[A-Z]{3}$')
    if not (iata.match(ticket.departure) or iata.match(ticket.destination)):
        raise InputError('Incorrect IATA code')

    if not ticket.return_date:
        ticket.return_date = ticket.outbound_date
    try:
        outbound_date = datetime.datetime.strptime(ticket.outbound_date, '%Y-%m-%d')
        return_date = datetime.datetime.strptime(ticket.return_date, '%Y-%m-%d')
    except ValueError:
        raise InputError('Incorrect format of date. Please use YYYY-MM-DD format.')

    if outbound_date > return_date:
        raise InputError('Outbound date after return date')
    now = datetime.datetime.now()
    if now > outbound_date or now > return_date:
        raise InputError('We do not provide time travel service')
    next_year = add_years(now, 1)
    if outbound_date > next_year or return_date > next_year:
        raise InputError('Flights date more than a year in the future')


def get_flights(ticket):
    oneway = '' if ticket.return_date else 'on'
    adult_count = '1'
    child_count = '0'
    infant_count = '0'

    with requests.Session() as session:
        search_url = 'https://www.flyniki.com/en/booking/flight/vacancy.php?'
        search_request = {
            'departure': ticket.departure,
            'destination': ticket.destination,
            'outboundDate': ticket.outbound_date,
            'returnDate': ticket.return_date,
            'oneway': oneway,
            'openDateOverview': '0',
            'adultCount': adult_count,
            'childCount': child_count,
            'infantCount': infant_count,
        }
        session_request = session.get(search_url, verify=False, data=search_request)
        session_request.raise_for_status()

        ajax_request = {
            '_ajax[templates][]': ['main'],
            '_ajax[requestParams][departure]': ticket.departure,
            '_ajax[requestParams][destination]': ticket.destination,
            '_ajax[requestParams][returnDeparture]': '',
            '_ajax[requestParams][returnDestination]': '',
            '_ajax[requestParams][outboundDate]': ticket.outbound_date,
            '_ajax[requestParams][returnDate]':	ticket.return_date,
            '_ajax[requestParams][adultCount]':	adult_count,
            '_ajax[requestParams][childCount]':	child_count,
            '_ajax[requestParams][infantCount]': infant_count,
            '_ajax[requestParams][openDateOverview]': '',
            '_ajax[requestParams][oneway]': oneway,
        }
        page_request = session.post(session_request.url, verify=False, data=ajax_request)
        page_request.raise_for_status()
    return page_request.json()


def detail_offer(raw_offer):
    details = re.compile(r'([A-Z\-]{7}), ([\d:\-]{11}), ([\da-z ]+), ([\w ]+): ([\d.,]+) (.+)')
    offer = details.match(raw_offer)
    return offer.groups()[1:]


def scrap_flights(page, direction):
    flights_table = page.xpath('//div[@id="vacancy_flighttable"]'
                               '/div[@class="wrapper"]'
                               '/div[@id="flighttables"]'
                               '/div[@class="%s block"]'
                               '/div[@class="tablebackground"]'
                               '/table[@class="flighttable"]' % direction)[0]

    currency = flights_table.xpath("thead/tr[2]/th[starts-with(@id, 'flight-table-header-price')]")[0].text
    flights = flights_table.xpath('tbody/tr/td[starts-with(@class, "fare")]/label/div[@class="lowest"]/span')

    flights = (i.attrib['title'] + currency for i in flights)
    return map(detail_offer, flights)


def search_flights(ticket):
    response = get_flights(ticket)
    if 'error' in response:
        error = html.fromstring(response['error'])
        error_msg = error.xpath('//div/div/p')[0].text
        raise RequestError(error_msg)

    seller_page = html.fromstring(response['templates']['main'])
    if not len(seller_page.xpath('//div[@id="vacancy_flighttable"]')):
        raise RequestError('No connections found for the entered data.')

    outbound_flights = scrap_flights(seller_page, 'outbound')
    if not ticket.return_date:
        for item in sorted(outbound_flights, key=lambda x: float(x[-2])):
            print(' '.join(item))
    else:
        return_flights = scrap_flights(seller_page, 'return')
        cross = itertools.product(outbound_flights, return_flights)
        cross_and_price = tuple(tuple([x[0], x[1], float(x[0][-2]) + float(x[1][-2])]) for x in cross)
        for item in sorted(cross_and_price, key=lambda x: x[2]):
            outbound_flight, return_flight, price = item
            print(' '.join(outbound_flight))
            print(' '.join(return_flight))
            print('Total coast: ' + str(price) + ' ' + outbound_flight[-1])
            print('')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Search flights')
    parser.add_argument('departure', type=str)
    parser.add_argument('destination', type=str)
    parser.add_argument('outbound_date', type=str)
    parser.add_argument('return_date', type=str, default='')
    args = parser.parse_args()

    Ticket = collections.namedtuple('Ticket', 'departure, destination, outbound_date, return_date,')
    input_ticket = Ticket(**vars(args))

    validate_input(input_ticket)
    search_flights(input_ticket)
    # search_flights('DME', 'BER', '2017-07-09', '2017-07-10')
