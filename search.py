"""
Simple flights scraper for www.flyniki.com
"""

import collections
import itertools
import argparse
import sys
import re
from datetime import datetime

import requests
from lxml import html


class InputError(Exception):
    """Exceptions raised for errors in user input"""
    pass


class RequestError(Exception):
    """Exceptions raised for errors on site side"""
    pass


def validate_input(ticket):
    iata = re.compile('^[A-Z]{3}$')
    if not (iata.match(ticket.departure) and iata.match(ticket.destination)):
        raise InputError('Incorrect IATA code')

    try:
        outbound_date = datetime.strptime(ticket.outbound_date, '%Y-%m-%d').date()
        if ticket.return_date:
            return_date = datetime.strptime(ticket.return_date, '%Y-%m-%d').date()
        else:
            return_date = outbound_date
    except ValueError:
        raise InputError(
            'Incorrect format of date. Please use YYYY-MM-DD format.')

    if outbound_date > return_date:
        raise InputError('Outbound date after return date')
    now = datetime.now().date()
    if now > outbound_date:
        raise InputError('We do not provide time travel service')
    if (return_date - now).days > 365:
        raise InputError('Flights date more than a year in the future')


def get_flights(ticket):
    one_way = '' if ticket.return_date else 'on'
    adult_count = '1'
    child_count = '0'
    infant_count = '0'

    with requests.Session() as session:
        search_url = 'https://www.flyniki.com/en/booking/flight/vacancy.php'
        search_request = {
            'departure': ticket.departure,
            'destination': ticket.destination,
            'outboundDate': ticket.outbound_date,
            'returnDate': ticket.return_date,
            'oneway': one_way,
            'openDateOverview': '0',
            'adultCount': adult_count,
            'childCount': child_count,
            'infantCount': infant_count,
        }
        session_request = session.get(search_url, data=search_request)
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
            '_ajax[requestParams][oneway]': one_way,
        }
        page_request = session.post(session_request.url, data=ajax_request)
        page_request.raise_for_status()
    return page_request.json()


def detail_offer(raw_offer):
    # DME-TXL, 08:55-13:55, 06 h 00 min , Economy Flex: 31,073.00 u'RUB'
    details = re.compile(r'[A-Z\-]{7},\s+([\d:\-]{11}),\s+([\d\sa-z]+),\s+([\w ]+):\s+([\d.,]+)\s+(.+)')
    offer = details.match(raw_offer)
    return offer.groups()


def scrap_flights(page, direction):
    flights_table = page.xpath('.//div[@class="%s block"]'
                               '/div[@class="tablebackground"]'
                               '/table[@class="flighttable"]' % direction)[0]

    currency = flights_table.xpath(
        'thead/tr/th[starts-with(@id, "flight-table-header-price")]')[0].text
    flights = flights_table.xpath(
        'tbody/tr/td[starts-with(@headers, "flight-table-header-price")]'
        '/label/div[@class="lowest"]/span')

    flights = (i.attrib['title'] + currency for i in flights)
    return map(detail_offer, flights)


def search_flights(ticket):
    print('Request flights from flyniki.com ...')
    response = get_flights(ticket)
    if 'error' in response:
        error = html.fromstring(response['error'])
        error_msg = error.xpath('./div/p')[0].text
        raise RequestError(error_msg)

    print('Process flights ...')
    seller_page = html.fromstring(response['templates']['main'])
    if not seller_page.xpath('./div[@id="vacancy_flighttable"]'):
        raise RequestError('No connections found for the entered data.')

    print('\nFlights found:\n')
    outbound_flights = scrap_flights(seller_page, 'outbound')

    def get_price(f):
        return float(f[-2].replace(',', ''))

    if not ticket.return_date:  # One way
        flights = enumerate(sorted(outbound_flights, key=get_price), start=1)
        for i, item in flights:
            print(u'No {}. {}'.format(i, ' '.join(item)))
    else:
        return_flights = scrap_flights(seller_page, 'return')
        cross = itertools.product(outbound_flights, return_flights)
        cross_and_price = ((x[0], x[1], get_price(x[0]) + get_price(x[1])) for x in cross)
        for i, item in enumerate(sorted(cross_and_price, key=lambda x: x[2]), start=1):
            outbound_flight, return_flight, price = item
            print 'No {}.'.format(i)
            print(' '.join(outbound_flight))
            print(' '.join(return_flight))
            print(u'Total coast: {} {}\n'.format(price, outbound_flight[-1]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Search flights')
    parser.add_argument('departure', type=str,
                        help='IATA code of departure point')
    parser.add_argument('destination', type=str,
                        help='IATA code of destination point')
    parser.add_argument('outbound_date', type=str,
                        help='Outbound date')
    parser.add_argument('return_date', type=str, nargs='?', default='',
                        help='Return date')
    args = parser.parse_args()

    Ticket = collections.namedtuple(
        'Ticket', 'departure, destination, outbound_date, return_date,')
    input_ticket = Ticket(**vars(args))

    try:
        validate_input(input_ticket)
        search_flights(input_ticket)
        sys.exit(0)
    except (InputError, RequestError, requests.exceptions.HTTPError) as e:
        sys.stderr.write(e.message)
        sys.exit(1)
