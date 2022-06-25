from requests_html import HTMLSession


def GamePass_Scraper():
    session = HTMLSession()

    response = session.get(
        'https://gamepasscounter.com/')
    
    # Take the response and parse it into a HTML object
    games = response.html.xpath('//*[@id="row2"]/div[2]/div[3]/div/ul')
    
    # Split the games into a list
    games=games[0].text.split('\n')

    
    print(f"{len(games)} games found ! \n")
    print(games)
    

# if script is run directly, run the scraper
if __name__ == '__main__':
    GamePass_Scraper()
