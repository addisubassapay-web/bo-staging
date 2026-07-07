import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("mercari_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export default api;

export const formatPrice = (n) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n || 0);

export const conditionLabel = (c) => {
  const map = {
    new: "New",
    like_new: "Like new",
    good: "Good",
    fair: "Fair",
    poor: "Poor",
  };
  return map[c] || c;
};
