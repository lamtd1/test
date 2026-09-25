import { RouterProvider, useRouter, Link } from "./lib/router";
import Chat from "./pages/Chat";
import Finance from "./pages/Finance";
import Shortlist from "./pages/Shortlist";
import SaleQueue from "./pages/SaleQueue";
import SaleReview from "./pages/SaleReview";

function Routes() {
  const { path } = useRouter();

  if (path === "/finance") return <Finance />;
  if (path === "/shortlist") return <Shortlist />;
  if (path === "/sale/queue") return <SaleQueue />;
  if (path === "/sale/review") return <SaleReview />;
  return <Chat />;
}

function Nav() {
  return (
    <nav className="topnav">
      <span className="brand">HomeMatch</span>
      <Link to="/">Chat</Link>
      <Link to="/finance">Tài chính</Link>
      <Link to="/shortlist">Shortlist</Link>
      <span className="sep" />
      <Link to="/sale/queue">Sale: Hàng chờ</Link>
    </nav>
  );
}

export default function App() {
  return (
    <RouterProvider>
      <Nav />
      <Routes />
    </RouterProvider>
  );
}
