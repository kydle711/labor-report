# LABOR REPORT

## Description

 A lightweight CLI tool for fetching and graphing KPIs of field technicians at my
 current employer. The script fetches data from Method CRM using the user's API
 key. The data is processed and stored in JSON. Customer reports can easily be
 generated through the CLI. Users can select the report type and date range for
 the report they would like. Once saved, the report can be viewed again, deleted,
 or graphed. Multiple reports can be plotted to the same graph for  comparisons.
 Data fetching is asynchronous for speed.

## Features

- asyncio
- httpx.AsyncClient requests
- rich progress bars, terminal prompts, and pretty printing
- error logging
- dotenv API key storage
- matplotlib graphing

## In Progress

- Testing
- More report types

## API Docs

- See [Method API](https://developer.method.me)
