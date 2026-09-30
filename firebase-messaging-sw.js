importScripts(
    "https://www.gstatic.com/firebasejs/12.19.0/firebase-app-compat.js"
);
importScripts(
    "https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging-compat.js"
);

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
        "[firebase-messaging-sw.js] Background message:",
        payload
    );

    const title =
        payload.data?.title ||
        payload.notification?.title ||
        "Blood Donor Emergency";

    const body =
        payload.data?.body ||
        payload.notification?.body ||
        "An emergency blood request has been received.";

    self.registration.showNotification(
        title,
        {
            body: body,
            icon: "/static/favicon.ico",
            badge: "/static/favicon.ico",
            tag:
                payload.data?.blood_group
                    ? `blood-request-${payload.data.blood_group}`
                    : "blood-request",
            data: {
                url: "/blood-request",
                ...payload.data
            }
        }
    );
});

self.addEventListener(
    "notificationclick",
    (event) => {
        event.notification.close();

        const targetUrl =
            event.notification?.data?.url ||
            "/blood-request";

        event.waitUntil(
            clients.matchAll({
                type: "window",
                includeUncontrolled: true
            }).then((clientList) => {
                for (const client of clientList) {
                    if (
                        "focus" in client &&
                        client.url.includes(
                            new URL(
                                targetUrl,
                                self.location.origin
                            ).pathname
                        )
                    ) {
                        return client.focus();
                    }
                }

                if (clients.openWindow) {
                    return clients.openWindow(
                        new URL(
                            targetUrl,
                            self.location.origin
                        ).href
                    );
                }
            })
        );
    }
);
