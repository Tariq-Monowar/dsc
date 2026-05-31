@echo off
REM Normal Chrome for scraping — no "automated test software" banner.
set CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe
if not exist "%CHROME%" set CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe
set PROFILE=%LocalAppData%\tripadvisor-scraper-chrome

start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%PROFILE%" https://www.tripadvisor.com/
