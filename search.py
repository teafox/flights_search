import argparse
import itertools
import datetime
import re

import requests
from lxml import html


def detail_offer(raw_offer):
    tmp_offer = raw_offer.split(', ')
    return tuple([tmp_offer[1], tmp_offer[2], tmp_offer[3].split(':')[0],
                  tmp_offer[3].split(':')[1].lstrip().split(' ')[0],
                  tmp_offer[3].split(':')[1].lstrip().split(' ')[1]])


def scrap_flights(page, direction):
    flights_table = page.xpath('//div[@id="vacancy_flighttable"]'
                               '/div[@class="wrapper"]'
                               '/div[@id="flighttables"]'
                               '/div[@class="%s block"]'
                               '/div[@class="tablebackground"]'
                               '/table[@class="flighttable"]' % direction)[0]

    currency = flights_table.xpath("thead/tr[2]/th[starts-with(@id, 'flight-table-header-price')]")[0].text
    flights = flights_table.xpath('tbody/tr/td[starts-with(@class, "fare")]/label/div[@class="lowest"]/span')

    used = set()
    flights = tuple(x for x in [i.attrib['title'] + currency for i in flights]
                    if x not in used and (used.add(x) or True))
    return map(detail_offer, flights)


def search_flights(departure, destination, outbound_date, return_date=''):

    oneway = 'on'
    adult_count = '1'
    child_count = '0'
    infant_count = '0'

    iata = re.compile('^[A-Z]{3}$')
    if not iata.match(departure):
        print 'Error: Incorrect IATA code of departure point.'
        return -1
    if not iata.match(destination):
        print 'Error: Incorrect IATA code of destination point.'
        return -1

    try:
        datetime.datetime.strptime(outbound_date, '%Y-%m-%d')
        if return_date:
            datetime.datetime.strptime(return_date, '%Y-%m-%d')
    except ValueError:
        print 'Incorrect format of outbound date. Please use YYYY-MM-DD format.'
        return -1
    if return_date:
        try:
            oneway = ''
            datetime.datetime.strptime(return_date, '%Y-%m-%d')
        except ValueError:
            print 'Incorrect format of return date. Please use YYYY-MM-DD format.'
            return -1

    session = requests.Session()
    search_request = {
        'departure': departure,
        'destination': destination,
        'outboundDate': outbound_date,
        'returnDate': return_date,
        'oneway': oneway,
        'openDateOverview': '0',
        'adultCount': adult_count,
        'childCount': child_count,
        'infantCount': infant_count,
    }

    try:
        session_request = session.get('https://www.flyniki.com/en/booking/flight/vacancy.php?', verify=False, data=search_request)
        session_request.raise_for_status()
    except requests.exceptions.RequestException as err:
        print err
        return -1

    ajax_request = {
        '_ajax[templates][]': ['main'],
        '_ajax[requestParams][departure]': departure,
        '_ajax[requestParams][destination]': destination,
        '_ajax[requestParams][returnDeparture]': '',
        '_ajax[requestParams][returnDestination]': '',
        '_ajax[requestParams][outboundDate]': outbound_date,
        '_ajax[requestParams][returnDate]':	return_date,
        '_ajax[requestParams][adultCount]':	adult_count,
        '_ajax[requestParams][childCount]':	child_count,
        '_ajax[requestParams][infantCount]': infant_count,
        '_ajax[requestParams][openDateOverview]': '',
        '_ajax[requestParams][oneway]': oneway,
    }

    try:
        page_request = session.post(session_request.url, verify=False, data=ajax_request)
        page_request.raise_for_status()
    except requests.exceptions.RequestException as err:
        print err
        return -1

    response = page_request.json()
    if 'error' in response:
        error = html.fromstring(response['error'])
        error_msg = error.xpath('//div/div/p')[0].text
        print error_msg
        return -1

    seller_page = html.fromstring(response['templates']['main'])
    if not len(seller_page.xpath('//div[@id="vacancy_flighttable"]')):
        print 'No connections found for the entered data.'
        return -1

    if oneway:
        outbound_flights = scrap_flights(seller_page, 'outbound')
        for item in sorted(outbound_flights, key=lambda x: float(x[-2])):
            print ' '.join(item)
    else:
        outbound_flights = scrap_flights(seller_page, 'outbound')
        return_flights = scrap_flights(seller_page, 'return')
        cross = itertools.product(outbound_flights, return_flights)
        cross_and_price = tuple(tuple([x[0], x[1], float(x[0][-2]) + float(x[1][-2])]) for x in cross)
        for item in sorted(cross_and_price, key=lambda x: x[2]):
            there, here, price = item
            print ' '.join(there)
            print ' '.join(here)
            print 'Total coast: ' + str(price) + ' ' + there[-1]
            print ''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Search flights')
    parser.add_argument('iata_from', type=str)
    parser.add_argument('iata_to', type=str)
    parser.add_argument('outbound_date', type=str)
    parser.add_argument('return_date', type=str, default='')

    args = parser.parse_args()
    search_flights(args.itai_from, args.itai_to, args.outbound_date, args.return_date)
    # search_flights('DME', 'BER', '2017-07-09', '2017-07-10')
