    await app.login_page.navigate()
    await app.login_page.enter_username("tomsmith")
    await app.login_page.enter_password("SuperSecretPassword!")
    await app.login_page.click_login()

    # Verify successful login
    assert await app.secure_page.is_on_secure_page()