click_element(11)  # Click on the search input field
fill_element(11, 'Ahmed Barakat')  # Fill the search input with 'Ahmed Barakat'
click_element(12)  # Click on the 'All' button to search for all messages
time.sleep(2 )  # Wait for the search results to load
click_element(116)  # Click on the first message from Ahmed Barakat
click_element(91)  # Click on the 'Add contact' button
time.sleep(  )  # Wait for the contact to be added
click_element(92)  # Click on the 'Ask Meta AI' button
time.sleep(  )  # Wait for the Meta AI chat to open
click_element(11)  # Click on the search input field again
fill_element(11, 'im iris')  # Fill the search input with 'im iris'
click_element(90)  # Click on the 'Send document' button
