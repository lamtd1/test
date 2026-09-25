import { createContext, useContext, useEffect, useState } from "react";

interface RouterState {
  path: string;
  query: URLSearchParams;
  navigate: (path: string) => void;
}

const RouterContext = createContext<RouterState | null>(null);

export function RouterProvider({ children }: { children: React.ReactNode }) {
  const [path, setPath] = useState(window.location.pathname);
  const [query, setQuery] = useState(new URLSearchParams(window.location.search));

  useEffect(() => {
    const onPop = () => {
      setPath(window.location.pathname);
      setQuery(new URLSearchParams(window.location.search));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = (to: string) => {
    window.history.pushState({}, "", to);
    const [p, q] = to.split("?");
    setPath(p);
    setQuery(new URLSearchParams(q ?? ""));
  };

  return (
    <RouterContext.Provider value={{ path, query, navigate }}>{children}</RouterContext.Provider>
  );
}

export function useRouter(): RouterState {
  const ctx = useContext(RouterContext);
  if (!ctx) throw new Error("useRouter must be used within RouterProvider");
  return ctx;
}

export function Link({ to, children, className }: { to: string; children: React.ReactNode; className?: string }) {
  const { navigate } = useRouter();
  return (
    <a
      href={to}
      className={className}
      onClick={(e) => {
        e.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}
