importScripts('https://www.gstatic.com/firebasejs/12.19.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging-compat.js');

firebase.initializeApp({
    apiKey: "AIzaSyA7gIg_Th_eXK0plcAymJI2jy1IqAakauY",
    authDomain: "blood-donor-management-s-c43cb.firebaseapp.com",
    projectId: "blood-donor-management-s-c43cb",
    storageBucket: "blood-donor-management-s-c43cb.firebasestorage.app",
    messagingSenderId: "333470584402",
    appId: "1:333470584402:web:1dbbc0319ca86e34e2198b"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
    console.log(
        "[firebase-messaging-sw.js] Received background message:",
        payload
    );

    const notificationTitle =
        payload.notification?.title || "Blood Donor Emergency";

    const notificationOptions = {
        body:
            payload.notification?.body ||
            "An emergency blood request has been received.",
        icon: "/static/favicon.ico"
    };

    self.registration.showNotification(
        notificationTitle,
        notificationOptions
    );
});