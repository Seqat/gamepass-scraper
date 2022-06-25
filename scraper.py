from requests_html import HTMLSession
import csv

def GamePass_Scraper(url,xpath):
    """_summary_: Scrapes the gamepass website for the games

    Args:
        url (_type_): URL of the website
        xpath (_type_): XPath of the list of games
    """
    session = HTMLSession()

    response = session.get(url
        )

    # Take the response and parse it into a HTML object
    games = response.html.xpath(xpath)

    # Split the games into a list
    games = games[0].text.split('\n')

    # prints the games
    game_printer(games)
    
    # writes the games to a csv file
    csv_writer(games)


def game_printer(games):
    """Summary: Prints the number of games in the list, and the games themselves

    Args:
        games (String): The list of games in string format
    """
    print(f"{len(games)} games found ! \n")

    for game in games:
        print(game)


def csv_writer(games):
    """Summary: Writes the games to a csv file

    Args:
        games (String): The list of games in string format
    """
    # Create a csv file and write the games to it
    with open('games.csv', 'w', encoding="UTF-8") as csv_file:
        writer = csv.writer(csv_file)
        
        for game in games:
            writer.writerow([game])
            
        


# if script is run directly, run the scraper
if __name__ == '__main__':
    GamePass_Scraper(   'https://gamepasscounter.com/',
                        '//*[@id="row2"]/div[2]/div[3]/div/ul')
